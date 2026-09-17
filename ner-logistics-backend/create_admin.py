import sqlite3
from app.services.auth_service import get_password_hash

h = get_password_hash('admin')
conn = sqlite3.connect('ner_logistics.db')
conn.execute('DELETE FROM users WHERE username="playwright_admin"')
conn.execute('INSERT INTO users (username, email, hashed_password, role, is_active) VALUES (?, ?, ?, ?, ?)', ('playwright_admin', 'playwright@example.com', h, 'admin', 1))
conn.commit()
print("success")
