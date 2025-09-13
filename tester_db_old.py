# db_tester.py 

import psycopg2
import json
import os
from backend.resume_improv_lib.generator import generate_resume_improvements
from backend.resume_improv_lib.new_resume_generator import build_new_resume
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
DB_HOST = "aws-0-us-east-1.pooler.supabase.com"
DB_NAME = "postgres"
DB_USER = "postgres.tcusahfctceuqzzrsiko"
DB_PASS = os.getenv("DB_PASSWORD", "")  # safer than hardcoding
DB_PORT = 6543  # supabase pooler usually uses 6543 

# --- LLM CONFIG ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY")) # type: ignore
llm_client = genai.GenerativeModel(model_name="gemini-2.5-flash") # type: ignore


def fetch_resume(row_id: int):
    conn = psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS, port=DB_PORT
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT id, resume_text, parsed_resume, analysis_result
        FROM resume_analyses
        WHERE id = %s
    """, (str(row_id),))   # cast to str for safety

    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


if __name__ == "__main__":
    # pick a test resume by ID
    row_id = "77ddeb6b-fbbb-48ad-9394-7dc6794001e4"  

    data = fetch_resume(row_id) # type: ignore
    if not data:
        print(f"No row found for id={row_id}")
    else:
        resume_id, resume_text, parsed_resume, analysis_result = data

        print("\n===== Fetched Resume From DB =====")
        print("resume_text:", (resume_text[:200] + "...") if resume_text else "None")
        print("parsed_resume:", parsed_resume)
        print("analysis_result:", analysis_result)
        
    if parsed_resume is None:
        print("⚠️ parsed_resume is None for this row. Skipping resume building.")
    else:
        # Generate suggestions
        suggestions = generate_resume_improvements(llm_client, analysis_result, parsed_resume)

        # Build improved resume
        new_resume = build_new_resume(parsed_resume, suggestions)

        # --- Print to console (pretty JSON) ---
        print("\n===== New Resume JSON =====")
        print(json.dumps(new_resume, indent=2))

        # --- Save to a .json file ---
        output_path = f"new_resume_{resume_id}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(new_resume, f, indent=2, ensure_ascii=False)

        print(f"\n✅ New resume JSON saved to {output_path}")
