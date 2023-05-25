import asyncio
import os

import aiohttp
from dotenv import load_dotenv


async def convert_file(source_file: str, target_format: str, folder: str):
    # Получаем API_KEY
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path)
    api_key = os.getenv('API_KEY')
    endpoint = "https://sandbox.zamzar.com/v1/jobs"

    # Настраиваем подключение к zamzar.com
    data = aiohttp.FormData()
    data.add_field('target_format', target_format)

    mp3_file_path = os.path.join(folder, source_file)
    data.add_field('source_file', open(mp3_file_path, 'rb'))
    check_status_auth = aiohttp.BasicAuth(login=api_key, password='')

    # cписок для ошибок ошибок
    converting_errors = []

    converting_file = ''

    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, data=data, auth=check_status_auth) as create_response:

            # Проверяем, что задача создана
            if create_response.status == 201:

                # Получем id задачи
                job_id = (await create_response.json())['id']

                # Эндпоинт задачи
                check_status_url = f'https://sandbox.zamzar.com/v1/jobs/{job_id}'

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

                                # Пытаемся скачать файл
                                result = await download_file(file_id, mp3_file_path, api_key)
                                if result == 'OK':
                                    converting_file = mp3_filename
                                else:
                                    converting_errors.append({source_file: result})
                                    break

                            elif job_status == 'failed':
                                converting_errors.append({source_file: 'Conversion failed'})
                                break

                        else:
                            converting_errors.append(
                                {source_file: f"Error checking job status: "
                                              f"{check_status.status} {check_status.reason}"})
                            break
            else:
                converting_errors.append(
                    {source_file: f"Error creating job: {create_response.status} {create_response.reason}"})

    return converting_file, converting_errors


async def download_file(file_id, mp3_file, api_key):
    # Эндпоинт для скачивания
    endpoint = f"https://sandbox.zamzar.com/v1/files/{file_id}/content"

    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, auth=aiohttp.BasicAuth(login=api_key, password='')) as response:
            try:
                with open(mp3_file, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024):
                        if chunk:
                            f.write(chunk)
                            f.flush()

                return "OK"

            except IOError as e:
                return str(e)


async def main():
    source_file = "sample-9s.wav"
    target_format = "mp3"
    folder_for_audio = '../audio/'
    result, errors = await convert_file(source_file, target_format, folder_for_audio)
    print(result, errors)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
