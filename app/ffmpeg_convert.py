import logging
import os

from pydub import AudioSegment

# Получение пользовательского логгера и установка уровня логирования
ffmpeg_convert_logger = logging.getLogger(__name__)
ffmpeg_convert_logger.setLevel(logging.INFO)

# Настройка обработчика и форматировщика
ffmpeg_convert_handler = logging.FileHandler(f"{__name__}.log", mode='w')
ffmpeg_convert_formatter = logging.Formatter("%(name)s %(asctime)s %(levelname)s %(message)s")

# добавление форматировщика к обработчику
ffmpeg_convert_handler.setFormatter(ffmpeg_convert_formatter)

# добавление обработчика к логгеру
ffmpeg_convert_logger.addHandler(ffmpeg_convert_handler)


def wav_to_mp3(wav_file: str, audio_folder: str, converting_errors=None):

    ffmpeg_convert_logger.info(f'Start convert {wav_file}')

    # cписок для ошибок ошибок
    if converting_errors is None:
        converting_errors = []
    else:
        converting_errors[:] = []

    wav_file_path = os.path.join(audio_folder, wav_file)
    mp3_filename = wav_file.replace('.wav', '.mp3')
    mp3_file_path = os.path.join(audio_folder, mp3_filename)

    # Конвертируем wav в mp3
    try:
        AudioSegment.from_wav(wav_file_path).export(mp3_file_path, format="mp3")
        ffmpeg_convert_logger.info(f'Convert complete: {mp3_filename}')
    except Exception as e:
        mp3_filename = ''
        ffmpeg_convert_logger.error(f'Error convert {wav_file}: {str(e)}')
        converting_errors.append({wav_file: f'Error convert: {str(e)}'})

    return mp3_filename, converting_errors


if __name__ == "__main__":
    # D:\projects\users_audio\audio\sample-3s.wav
    wav_audio_file = 'sample-3s.wav'
    folder_for_audio = 'D:/projects/users_audio/audio/'
    converted_to_mp3, errors = wav_to_mp3(wav_audio_file, folder_for_audio)
    print(converted_to_mp3, errors, sep='\n')
