import logging
import os
import re
import uuid
from typing import List

from dotenv import load_dotenv
from fastapi import (Depends, FastAPI, File, Header, HTTPException, Response,
                     UploadFile)
from pydantic import BaseModel, Field, validator
from sqlalchemy.exc import DatabaseError, IntegrityError
from starlette.responses import FileResponse

from .async_wav_to_mp3 import convert_file
from .config import settings
from .db import AudioRecord, SessionLocal, User
from .ffmpeg_convert import wav_to_mp3
from .start_app import create_table

# Получение пользовательского логгера и установка уровня логирования
main_logger = logging.getLogger(__name__)
main_logger.setLevel(logging.INFO)

# Настройка обработчика и форматировщика
main_handler = logging.FileHandler(f"{__name__}.log", mode='w')
main_formatter = logging.Formatter("%(name)s %(asctime)s %(levelname)s %(message)s")

# добавление форматировщика к обработчику
main_handler.setFormatter(main_formatter)

# добавление обработчика к логгеру
main_logger.addHandler(main_handler)

# Папка для хранения аудио файлов
folder_for_audio = '../audio/'

# Узнаем режим работы (самостоятельный или с помощью внешнего api)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)
FFMPEG = os.getenv('FFMPEG')

# Максимальное число принимаемых файлов
MAX_FILES = int(os.getenv('MAX_FILES'))

app = FastAPI()


# Проверка и валидация имени пользователя
class UserCreateRequest(BaseModel):
    name: str = Field(..., description='User name')

    @validator('name')
    def validate_name(cls, name):
        pattern = r'^[a-zA-Zа-яА-Я0-9_-]+$'
        if not re.search(pattern, name):
            main_logger.exception(f'Incorrect name: {name}')
            raise ValueError('Name can contain only letters, numbers, "_" and "-"')
        return name


# Проверка id и токена пользователя
class AudioCreateRequest(BaseModel):
    user_id: int = Field(..., description='User ID')
    token: str = Field(..., description='Access token')


# Получаем id и токен из заголовка
async def get_audio_create_request(
    user_id: int = Header(..., alias='X-User-ID'),
    token: str = Header(..., alias='X-Token'),

):
    return AudioCreateRequest(user_id=user_id, token=token)


# Валидация аудиофайла
def validate_audiofile(file):
    pattern = r'^[a-zA-Zа-яА-Я0-9_-]+\.wav+$'
    if re.match(pattern, file):
        return True
    return False


def validator_token(token):
    pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    if re.match(pattern, token):
        return True
    else:
        main_logger.exception('Request attempt with a token containing unacceptable characters')
        raise HTTPException(status_code=401, detail='Token containing unacceptable characters')


# Добавляем пользователя, принимаем имя, возвращаем id + token
@app.post('/users')
async def create_user(user_request: UserCreateRequest):

    try:
        with SessionLocal() as session:

            # Проверяем имя пользователя на уникальность
            user_check = session.query(User).filter_by(name=user_request.name).first()

            if user_check is not None:
                raise HTTPException(status_code=409, detail=f'User: {user_request.name} already exists')

            # Генерируем токен
            token = str(uuid.uuid4())
            main_logger.info(f'Generation uuid token for user: {user_request.name}')

            user = User(name=user_request.name, token=token)

            session.add(user)
            session.commit()
            user_id = user.id
            main_logger.info(f'Save user: {user_id}')

            # Добавляем токен и имя пользователя в headers
            response = Response()
            response.headers['X-Token'] = token
            response.headers['X-User-ID'] = str(user_id)

            return response

    except IntegrityError:
        main_logger.exception(f'Try add already exists user: {user_request.name}')
        raise HTTPException(status_code=409, detail=f'User: {user_request.name} already exists')

    except DatabaseError as e:
        main_logger.exception(f'Invalid access to database {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=f'Invalid access to database {str(e)}')


# Обработка аудио файлов
@app.post('/audio')
async def add_audio(audio_request: AudioCreateRequest = Depends(get_audio_create_request),
                    audio_files: List[UploadFile] = File(description="Audio files")):

    # Ограничение числа отправляемых файлов
    if len(audio_files) > MAX_FILES:
        main_logger.exception(f'Two many files to upload: {len(audio_files)}')
        raise HTTPException(status_code=400, detail='Too many audio files. Maximum allowed is 5.')

    # Валидация токена
    validator_token(audio_request.token)

    with SessionLocal() as session:

        # Проверяем пользователя
        user = session.query(User).filter_by(id=audio_request.user_id, token=audio_request.token).first()
        if not user:
            main_logger.exception(f'User: {audio_request.user_id} not found or wrong token')
            raise HTTPException(status_code=401, detail='Invalid user ID or token')
        main_logger.info(f'User: {audio_request.user_id} add {len(audio_files)} files in convert')

        # список успешных и безуспешных обработок файлов
        successful_urls = []
        failed_files = []

        # Проверка наличия папки "audio"
        if not os.path.exists(folder_for_audio):
            os.makedirs(folder_for_audio)
            main_logger.info('Create folder for audio files')

        for audio_file in audio_files:

            # Валидация имени файла
            if validate_audiofile(audio_file.filename):
                audio_id = str(uuid.uuid4())
                wav_audio_file = f'{os.path.basename(audio_file.filename).rstrip(".wav")}-{audio_id}.wav'
                wav_file_path = os.path.join(folder_for_audio, wav_audio_file)
                main_logger.info(f'Generation uuid for wav-audio: {wav_file_path}')

                try:
                    # Сохраняем полученный WAV файл
                    with open(wav_file_path, 'wb') as wav_file:
                        wav_file.write(await audio_file.read())
                        main_logger.info('Save wav-audio')

                except Exception as e:

                    # Удаляем временный файл WAV
                    os.remove(wav_file_path)
                    main_logger.exception(f'Error save {wav_file_path}, delete temp wav file')
                    raise HTTPException(status_code=500, detail=str(e))

                # Выбираем способ конвертации
                if FFMPEG == 'yes':

                    # Преобразование WAV в MP3 с помощью ffmpeg
                    converted_to_mp3, errors = wav_to_mp3(wav_audio_file, folder_for_audio)
                elif FFMPEG == 'no':

                    # Преобразуем WAV в MP3 с помощью стороннего API
                    converted_to_mp3, errors = await convert_file(wav_audio_file, "mp3", folder_for_audio)
                else:
                    raise HTTPException(status_code=404,
                                        detail='Need to choose the conversion mode: ffmpeg or external api')

                # Сохраняем ошибку при обработке конкретного файла
                if errors:
                    failed_files.append({f'{audio_file.filename} fail in request to api zamzar.com': f'{errors}'})
                    main_logger.error(f'{audio_file.filename} fail in request to api zamzar.com: {errors}')

                # если есть сконвериторованный файл
                if converted_to_mp3:
                    main_logger.info(f'Convert {converted_to_mp3}')

                    # Сохраняем информацию об аудиозаписи в базе данных
                    audio_recording = AudioRecord(id=audio_id, file_name=converted_to_mp3, user=user)

                    try:
                        session.add(audio_recording)
                        session.commit()
                        main_logger.info(f'Mp3 save with id: {audio_id}')
                    except Exception as e:
                        main_logger.exception(f'Invalid access to database {e}', exc_info=True)
                        raise HTTPException(status_code=500, detail=f'Invalid access to database {e}')

                    download_url = f'http://{settings.host_url}/record?id={audio_id}&user={audio_request.user_id}'
                    successful_urls.append(download_url)
                    main_logger.info(
                        f'Add http://{settings.host_url}/record?id={audio_id}&user={audio_request.user_id}'
                    )

                # Удаляем временный файл WAV
                os.remove(wav_file_path)
                main_logger.info(f'Delete temp {wav_file_path}')

            else:
                failed_files.append({audio_file.filename: "No .wav audiofile"})
                main_logger.error(f'{audio_file.filename}: No .wav audiofile')

    return {'successful_urls': successful_urls, 'failed_files': failed_files}


@app.get('/record')
async def get_audio_record(id: str, user: str):

    # Валидация id файла
    validator_token(id)

    # Валидация user
    if not user.isalnum():
        main_logger.exception('Wrong user id with try to download mp3')
        raise HTTPException(status_code=404, detail='Audio recording not found')

    with SessionLocal() as session:

        user = session.query(User).filter_by(id=user).first()
        if not user:
            main_logger.exception(f'User: {user} not found')
            raise HTTPException(status_code=404, detail='User not found')

        audio_recording = session.query(AudioRecord).filter_by(id=id, user_id=user.id).first()
        if not audio_recording:
            main_logger.exception(f'Audio record {id} not found')
            raise HTTPException(status_code=404, detail='Audio recording not found')

        # Получаем абсолютный путь до папки с аудиофайлами
        audio_file_path = os.path.join(folder_for_audio, audio_recording.file_name)

        if not os.path.exists(audio_file_path):
            main_logger.exception('Path not found')
            raise HTTPException(status_code=404,
                                detail=f'Audio file not found {audio_file_path, audio_recording.file_name}')

        return FileResponse(audio_file_path, filename=audio_recording.file_name)


@app.on_event("startup")
async def startup():
    main_logger.info("Start app")
    # Создаем таблицы
    create_table()
    main_logger.info("Create tables")


@app.on_event("shutdown")
async def shutdown():
    main_logger.info("Shutdown")
    SessionLocal.close_all()
    main_logger.info("Close all sessions")
