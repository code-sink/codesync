from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base
import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = (
    os.environ["DB_URL"]
)

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,  
    connect_args={"prepare_threshold": None},
    execution_options={"prepared_statement_cache_size": None}, 
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

async def create_all_tables():
    print("Attempting to create tables...")
    async with engine.begin() as conn:
        tables = list(Base.metadata.tables.keys())
        print(f"Tables registered in metadata: {tables}")
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully.")

