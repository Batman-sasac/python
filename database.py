import psycopg2
import os
from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(url, key)