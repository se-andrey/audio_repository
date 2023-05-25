from sqlalchemy import create_engine, inspect

from .config import settings
from .db import AudioRecord, User


# Создание таблиц
def create_table():
    engine = create_engine(settings.db_url)
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Если таблиц нет, то создаем
    if AudioRecord.__tablename__ not in existing_tables:
        AudioRecord.metadata.create_all(bind=engine)

    if User.__tablename__ not in existing_tables:
        User.metadata.create_all(bind=engine)
