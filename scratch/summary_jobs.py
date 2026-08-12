import sqlite3

conn = sqlite3.connect("data/jobs.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

selected_jobs = c.execute("""
    SELECT id, company, title, location, deterministic_score, ai_score, final_score, status, application_url, resume_pdf_path 
    FROM jobs 
    WHERE status = 'selected'
    ORDER BY final_score DESC
""").fetchall()

print(f"\n--- TOP 10 SELECTED JOBS FROM RUN #3 ---")
for idx, j in enumerate(selected_jobs, 1):
    det_sc = j['deterministic_score'] if j['deterministic_score'] is not None else 0.0
    ai_sc = j['ai_score'] if j['ai_score'] is not None else 0.0
    fin_sc = j['final_score'] if j['final_score'] is not None else 0.0
    has_resume = "Generated" if j["resume_pdf_path"] else "Not Generated"
    print(f"{idx:2d}. #{j['id']:<4} | {j['company']:<24} | {j['title']:<48} | Final Score: {fin_sc:<5.1f} (Det: {det_sc:<4.1f}, AI: {ai_sc:<4.1f}) | {j['location']}")
