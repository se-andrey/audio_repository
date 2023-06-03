import asyncio
import logging
import os

import aiohttp
from dotenv import load_dotenv

# Получение пользовательского логгера и установка уровня логирования
wav_to_mp3_logger = logging.getLogger(__name__)
wav_to_mp3_logger.setLevel(logging.INFO)

# Настройка обработчика и форматировщика
wav_to_mp3_handler = logging.FileHandler(f"{__name__}.log", mode='w')
wav_to_mp3_formatter = logging.Formatter("%(name)s %(asctime)s %(levelname)s %(message)s")

# добавление форматировщика к обработчику
wav_to_mp3_handler.setFormatter(wav_to_mp3_formatter)

# добавление обработчика к логгеру
wav_to_mp3_logger.addHandler(wav_to_mp3_handler)


async def convert_file(source_file: str, target_format: str, folder: str, converting_errors=None):
    # Получаем API_KEY
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path)
    api_key = os.getenv('API_KEY')
    endpoint = "https://sandbox.zamzar.com/v1/jobs"

    # Настраиваем подключение к zamzar.com
    data = aiohttp.FormData()
    data.add_field('target_format', target_format)

    wav_file_path = os.path.join(folder, source_file)
    data.add_field('source_file', open(wav_file_path, 'rb'))
    check_status_auth = aiohttp.BasicAuth(login=api_key, password='')
    wav_to_mp3_logger.info(f'Status: {check_status_auth} for file:{wav_file_path}')

    # cписок для ошибок
    if converting_errors is None:
        converting_errors = []
    else:
        converting_errors[:] = []

    converting_file = ''

    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, data=data, auth=check_status_auth) as create_response:

            # Проверяем, что задача создана
            if create_response.status == 201:

                # Получем id задачи
                job_id = (await create_response.json())['id']
                wav_to_mp3_logger.info(f'Task to convert created, id:{job_id}')

                # Эндпоинт задачи
                check_status_url = f'https://sandbox.zamzar.com/v1/jobs/{job_id}'

                wav_to_mp3_logger.info('Starting waiting for completed task')

                # Ожидаем окончания обработки файла
                while True:

                    # Асинхронный sleep на 1 секунду
                    await asyncio.sleep(1)

                    async with session.get(check_status_url, auth=check_status_auth) as check_status:
                        if check_status.status == 200:

                            # Получаем статус задачи
                            job_status = (await check_status.json())['status']

                            # Проверяем статус
                            if job_status == 'successful':
                                file_id = (await check_status.json())['target_files'][0]['id']
                                mp3_filename = source_file.replace('.wav', '.mp3')
                                mp3_file_path = os.path.join(folder, mp3_filename)

                                wav_to_mp3_logger.info(f'Task complete, file_id:{file_id}')

                                # Пытаемся скачать файл
                                result = await download_file(file_id, mp3_file_path, api_key)

                                if result == 'OK':
                                    converting_file = mp3_filename
                                    wav_to_mp3_logger.info(f'File: {converting_file} is downloaded')
                                else:
                                    converting_errors.append({source_file: result})
                                    wav_to_mp3_logger.error(f'Error convert file: {source_file}, result: {result}')
                                break

                            elif job_status == 'failed':
                                wav_to_mp3_logger.error(f'{source_file}: Conversion failed')
                                converting_errors.append({source_file: 'Conversion failed'})
                                break

                        else:
                            wav_to_mp3_logger.error(f'{source_file}: Error checking job status:'
                                                    f'{check_status.status} {check_status.reason}')
                            converting_errors.append(
                                {source_file: f"Error checking job status: "
                                              f"{check_status.status} {check_status.reason}"})
                            break
            else:
                wav_to_mp3_logger.error(f'{source_file}: Error creating job:'
                                        f'{create_response.status} {create_response.reason}')
                converting_errors.append(
                    {source_file: f"Error creating job: {create_response.status} {create_response.reason}"})

    return converting_file, converting_errors


async def download_file(file_id, mp3_file, api_key):
    # Эндпоинт для скачивания
    endpoint = f"https://sandbox.zamzar.com/v1/files/{file_id}/content"
    wav_to_mp3_logger.info('Start downloading file')

    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, auth=aiohttp.BasicAuth(login=api_key, password='')) as response:
            try:
                with open(mp3_file, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024):
                        if chunk:
                            f.write(chunk)
                            f.flush()
                wav_to_mp3_logger.info('Download complete')
                return "OK"

            except IOError as e:
                wav_to_mp3_logger.exception(f'{str(e)}')
                return str(e)


async def main():
    source_file = "sample-3s.wav"
    target_format = "mp3"
    folder_for_audio = '../audio/'
    result, errors = await convert_file(source_file, target_format, folder_for_audio)
    print(result, errors, sep='\n')


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.run(main())
