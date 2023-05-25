import os
import uuid
from typing import List

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from .async_wav_to_mp3 import convert_file
from .config import settings
from .db import AudioRecord, SessionLocal, User
from .start_app import create_table

app = FastAPI()

# Папка для хранения аудио файлов
folder_for_audio = '../audio/'


class UserCreateRequest(BaseModel):
    name: str = Field(..., description="User name")


class UserCreateResponse(BaseModel):
    user_id: str = Field(..., description="User ID")
    token: str = Field(..., description="Access token")


class AudioCreateRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    token: str = Field(..., description="Access token")


class AudioCreateResponse(BaseModel):
    successful_urls: List[str] = Field(..., description="URLs for successful audio conversions")
    failed_files: List[dict] = Field(..., description="Names of failed audio files")


class AudioGetResponse(BaseModel):
    file: str = Field(..., description="Audio file")


# Добавляем пользователя, принимаем имя, возвращаем id + token
@app.post('/users', response_model=UserCreateResponse)
async def create_user(user_request: UserCreateRequest):
    user_id = str(uuid.uuid4())
    token = str(uuid.uuid4())
    user = User(id=user_id, name=user_request.name, token=token)

    try:
        with SessionLocal() as session:
            session.add(user)
            session.commit()
            user_id = user.id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Invalid access to database {e}')

    return {'user_id': user_id, 'token': token}


@app.post('/audio', response_model=AudioCreateResponse)
async def add_audio(audio_request: AudioCreateRequest = Depends(),
                    audio_files: List[UploadFile] = File(..., description="Audio files")):
    with SessionLocal() as session:
        user = session.query(User).filter_by(id=audio_request.user_id, token=audio_request.token).first()
        if not user:
            raise HTTPException(status_code=401, detail='Invalid user ID or token')

        successful_urls = []
        failed_files = []

        # Проверка наличия папки "audio"
        if not os.path.exists(folder_for_audio):
            os.makedirs(folder_for_audio)

        for audio_file in audio_files:
            if audio_file.filename.endswith('.wav'):
                audio_id = str(uuid.uuid4())
                wav_audio_file = f'{os.path.basename(audio_file.filename).rstrip(".wav")}-{audio_id}.wav'
                wav_file_path = os.path.join(folder_for_audio, wav_audio_file)

                try:

                    # Сохраняем полученный WAV файл
                    with open(wav_file_path, 'wb') as wav_file:
                        wav_file.write(await audio_file.read())

                    # Преобразуем WAV в MP3
                    converted_to_mp3, errors = await convert_file(wav_audio_file, "mp3", folder_for_audio)

                    # Сохраняем ошибку при обработке конкретного файла
                    if errors:
                        failed_files.append(
                            {f'{audio_file.filename} fail in request to api zamzar.com': f'{errors}'})

                    # если есть сконвериторованный файл
                    if converted_to_mp3:

                        # Сохраняем информацию об аудиозаписи в базе данных
                        audio_recording = AudioRecord(id=audio_id, file_name=converted_to_mp3, user=user)
                        try:
                            session.add(audio_recording)
                            session.commit()
                        except Exception as e:
                            raise HTTPException(status_code=500, detail=f'Invalid access to database {e}')

                        download_url = f'http://{settings.host_url}/record?id={audio_id}&user={audio_request.user_id}'
                        successful_urls.append(download_url)

                    # Удаляем временный файл WAV
                    os.remove(wav_file_path)

                except Exception as e:
                    failed_files.append(
                        {f'{audio_file.filename} try save and convert .wav to .mp3': f'{str(e)} {errors}'})
            else:
                failed_files.append({audio_file.filename: "No .wav audiofile"})

    return {'successful_urls': successful_urls, 'failed_files': failed_files}


@app.get('/record')
async def get_audio_record(id: str, user: str):
    with SessionLocal() as session:

        user = session.query(User).filter_by(id=user).first()
        if not user:
            raise HTTPException(status_code=404, detail='User not found')

        audio_recording = session.query(AudioRecord).filter_by(id=id, user_id=user.id).first()
        if not audio_recording:
            raise HTTPException(status_code=404, detail='Audio recording not found')

        # Получаем абсолютный путь до папки с аудиофайлами
        audio_file_path = os.path.join(folder_for_audio, audio_recording.file_name)

        if not os.path.exists(audio_file_path):
            raise HTTPException(status_code=404,
                                detail=f'Audio file not found {audio_file_path, audio_recording.file_name}')

        return FileResponse(audio_file_path, filename=audio_recording.file_name)


@app.get("/")
async def read_root():
    return {"hello": "world"}


@app.on_event("startup")
async def startup():

    # Создаем таблицы
    create_table()


@app.on_event("shutdown")
async def shutdown():
    SessionLocal.close_all()
