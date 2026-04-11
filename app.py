# *** SECURITY LAYER 1: ENHANCED IMPORTS FOR AUTHENTICATION & USER TRACKING ***
from flask import Flask, render_template, request, make_response
# from flask import Flask, render_template, request, make_response, session, redirect, url_for  # Commented out session, redirect, url_for
from rag import generate_questions
import secrets
import hashlib
import json
# *** END SECURITY LAYER 1 ***
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import datetime, timedelta
import io
import os

app = Flask(__name__)
# *** SECURITY LAYER 1: ENHANCED SECRET KEY GENERATION ***
# app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))  # COMMENTED OUT - Session management disabled
# *** END SECURITY LAYER 1 ***

# *** SECURITY LAYER 2: USER AUTHENTICATION & USAGE TRACKING SETUP ***
# User usage file for tracking requests per user
# USAGE_FILE = 'user_usage.json'  # COMMENTED OUT - Session management disabled

# def load_user_usage():
#     """Load user usage data from JSON file"""
#     if os.path.exists(USAGE_FILE):
#         with open(USAGE_FILE, 'r') as f:
#             return json.load(f)
#     return {}

# def save_user_usage(usage_data):
#     """Save user usage data to JSON file"""
#     with open(USAGE_FILE, 'w') as f:
#         json.dump(usage_data, f)
# *** END SECURITY LAYER 2 SETUP ***

# Rate limiting storage (in-memory for free tier)
# Format: {ip: {'count': int, 'reset_time': datetime}}
RATE_LIMIT_STORAGE = {}

# Rate limit settings
REQUESTS_PER_HOUR = 5  # Free tier: 10 papers per hour per IP
REQUESTS_PER_DAY = 20   # Free tier: 30 papers per day per IP

def check_rate_limit(ip_address):
    """Check if IP has exceeded rate limits"""
    now = datetime.now()
    
    # Clean up old entries (older than 24 hours)
    cleanup_time = now - timedelta(days=1)
    for ip in list(RATE_LIMIT_STORAGE.keys()):
        # Check both reset times - if both older than cleanup_time, remove
        if (RATE_LIMIT_STORAGE[ip]['hourly_reset'] < cleanup_time and 
            RATE_LIMIT_STORAGE[ip]['daily_reset'] < cleanup_time):
            del RATE_LIMIT_STORAGE[ip]
    
    # Get or create IP entry
    if ip_address not in RATE_LIMIT_STORAGE:
        RATE_LIMIT_STORAGE[ip_address] = {
            'hourly_count': 0,
            'hourly_reset': now + timedelta(hours=1),
            'daily_count': 0,
            'daily_reset': now + timedelta(days=1)
        }
    
    ip_data = RATE_LIMIT_STORAGE[ip_address]
    
    # Reset hourly counter if time has passed
    if now > ip_data['hourly_reset']:
        ip_data['hourly_count'] = 0
        ip_data['hourly_reset'] = now + timedelta(hours=1)
    
    # Reset daily counter if time has passed
    if now > ip_data['daily_reset']:
        ip_data['daily_count'] = 0
        ip_data['daily_reset'] = now + timedelta(days=1)
    
    # Check limits
    if ip_data['hourly_count'] >= REQUESTS_PER_HOUR:
        minutes_left = int((ip_data['hourly_reset'] - now).total_seconds() / 60)
        return False, f"⏰ Rate limit: {REQUESTS_PER_HOUR} papers/hour. Try again in {minutes_left} minutes."
    
    if ip_data['daily_count'] >= REQUESTS_PER_DAY:
        hours_left = int((ip_data['daily_reset'] - now).total_seconds() / 3600)
        return False, f"⏰ Daily limit: {REQUESTS_PER_DAY} papers/day. Try again in {hours_left} hours."
    
    # Increment counters
    ip_data['hourly_count'] += 1
    ip_data['daily_count'] += 1
    
    return True, f"✅ Used: {ip_data['hourly_count']}/{REQUESTS_PER_HOUR} (hour), {ip_data['daily_count']}/{REQUESTS_PER_DAY} (day)"

# *** SECURITY LAYER 3: USER LOGIN ROUTE ***
# COMMENTED OUT - Session management disabled
# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     """User login endpoint - WARNING: Hardcoded credentials for demo. Use database in production!"""
#     if request.method == 'POST':
#         username = request.form.get('username', '')
#         password = request.form.get('password', '')
#         # ⚠️ SECURITY NOTE: This is a simple demo authentication.
#         # TODO: Move to proper database with hashed passwords for production!
#         if username == "teacher1" and password == "tpal123":
#             session['user'] = username
#             return redirect(url_for('home'))
#         else:
#             return render_template("index.html", questions="❌ Invalid credentials, please try again."), 401
#     return '''<!DOCTYPE html>
#     <html>
#     <head><title>T-Pal Login</title>
#     <style>
#         body { font-family: Arial; margin: 50px; }
#         form { max-width: 300px; }
#         input { display: block; margin: 10px 0; padding: 8px; width: 100%; }
#         input[type="submit"] { cursor: pointer; background-color: #4CAF50; color: white; border: none; }
#     </style>
#     </head>
#     <body>
#     <h2>T-Pal Teacher Login</h2>
#     <form method="post">
#         <label for="username"><b>Username:</b></label>
#         <input type="text" name="username" id="username" required>
#         <label for="password"><b>Password:</b></label>
#         <input type="password" name="password" id="password" required>
#         <input type="submit" value="Login">
#     </form>
#     <p><small>Demo: username | password</small></p>
#     </body>
#     </html>'''
# *** END SECURITY LAYER 3 ***

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    try:
        # *** SECURITY LAYER 2 & 3: USER AUTHENTICATION CHECK ***
        # Check if user is logged in via session
        # if not session.get('user'):
        #     return render_template("index.html", 
        #                          questions="❌ Please login first. <a href='/login'>Click here to Login</a>",
        #                          subject="",
        #                          class_num="",
        #                          chapter=""), 401
        
        # Load user usage data and check if trial limit exceeded
        # COMMENTED OUT - Session management disabled
        # usage_data = load_user_usage()
        # user_data = usage_data.get(session['user'], {'requests_made': 0, 'trial_limit': 10})
        # 
        # if user_data['requests_made'] >= user_data['trial_limit']:
        #     return render_template("index.html",
        #                            questions=f"❌ Your free trial limit ({user_data['trial_limit']} requests) has been used.<br>Requests used: {user_data['requests_made']}/{user_data['trial_limit']}<br>Please contact admin.",
        #                            subject="",
        #                            class_num="",
        #                            chapter="")
        # *** END SECURITY LAYER 2 & 3 CHECK ***
        
        # Get client IP address
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        
        # Check rate limit
        allowed, message = check_rate_limit(ip_address)
        if not allowed:
            return render_template("index.html", 
                                 questions=f"❌ {message}\n\nFree tier limits prevent abuse. If you need more, please contact us for a premium account.",
                                 subject="",
                                 class_num="",
                                 chapter="")
        
        # Log rate limit status
        print(message)
        
        # Get form data (FIX: use .get() instead of direct access)
        subject = request.form.get("subject", "Mathematics")
        class_num = request.form.get("class_num", "8")
        chapter = request.form.get("chapter", "")
        num_q = request.form.get("num_questions", "10")
        difficulty = request.form.get("difficulty", "Medium")
        question_type = request.form.get("question_type", "Mixed")  # FIX: was request.form["question_type","Mixed"]
        
        print(f"📊 Generating: {subject}, Class {class_num}, {chapter}, Type: {question_type}")
        
        result = generate_questions(subject, class_num, chapter, num_q, difficulty, question_type)
        
        # *** SECURITY LAYER 2 & 3: INCREMENT USER REQUEST COUNTER ***
        # Track this successful generation request for the logged-in user
        # COMMENTED OUT - Session management disabled
        # user_data['requests_made'] += 1
        # usage_data[session['user']] = user_data
        # save_user_usage(usage_data)
        # print(f"📊 User '{session['user']}' usage updated: {user_data['requests_made']}/{user_data['trial_limit']} requests used")
        # *** END SECURITY LAYER 2 & 3 TRACKING ***
        
        return render_template("index.html", 
                             questions=result,
                             subject=subject,
                             class_num=class_num,
                             chapter=chapter,
                             rate_limit_info=message)
    except Exception as e:
        print(f"❌ ERROR in generate route: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500

# *** SECURITY LAYER 3: ADMIN DASHBOARD ROUTE ***
# COMMENTED OUT - Session management disabled
# @app.route('/admin', methods=['GET'])
# def admin():
#     """Admin dashboard to view user usage statistics"""
#     # ⚠️ SECURITY NOTE: Check if user is 'teacher1' (the admin user)
#     if session.get('user') != 'teacher1':
#         return render_template("index.html", questions="❌ Access Denied! Only admin (teacher1) can view this page."), 401
#     
#     # Load and display all user usage data
#     usage_data = load_user_usage()
#     
#     # Build HTML table for admin dashboard
#     admin_html = '''<!DOCTYPE html>
#     <html>
#     <head>
#         <title>T-Pal Admin Dashboard</title>
#         <style>
#             body { font-family: Arial; margin: 20px; }
#             table { border-collapse: collapse; width: 100%; margin-top: 20px; }
#             th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
#             th { background-color: #4CAF50; color: white; }
#             tr:nth-child(even) { background-color: #f2f2f2; }
#             .stats { background-color: #e7f3fe; padding: 10px; margin-bottom: 20px; border-radius: 5px; }
#         </style>
#     </head>
#     <body>
#         <h1>👨‍💼 T-Pal Admin Dashboard</h1>
#         <a href="/logout" style="color: red; text-decoration: underline;">Logout</a>
#         
#         <div class="stats">
#             <h3>📊 System Statistics</h3>
#             <p><b>Total Users:</b> {total_users}</p>
#             <p><b>Total Requests Made:</b> {total_requests}</p>
#         </div>
#         
#         <h2>User Usage Details</h2>
#         <table>
#             <tr>
#                 <th>Username</th>
#                 <th>Requests Made</th>
#                 <th>Trial Limit</th>
#                 <th>Status</th>
#             </tr>
#             {table_rows}
#         </table>
#     </body>
#     </html>'''
#     
#     # Calculate statistics
#     total_users = len(usage_data)
#     total_requests = sum([user['requests_made'] for user in usage_data.values()])
#     
#     # Build table rows
#     table_rows = ""
#     for user, data in usage_data.items():
#         status = "✅ Active" if data['requests_made'] < data['trial_limit'] else "❌ Limit Reached"
#         table_rows += f"<tr><td>{user}</td><td>{data['requests_made']}</td><td>{data['trial_limit']}</td><td>{status}</td></tr>\n"
#     
#     admin_html = admin_html.format(
#         total_users=total_users,
#         total_requests=total_requests,
#         table_rows=table_rows
#     )
#     
#     return admin_html
# *** END SECURITY LAYER 3 ***

# *** SECURITY LAYER 1: LOGOUT ROUTE ***
# COMMENTED OUT - Session management disabled
# @app.route('/logout')
# def logout():
#     """Simple logout - clears session"""
#     session.clear()
#     return redirect('/login')
# *** END SECURITY LAYER 1 ***

@app.route("/download", methods=["POST"])
def download():
    questions = request.form["questions"]
    subject = request.form["subject"]
    class_num = request.form["class_num"]
    chapter = request.form["chapter"]
    
    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                           rightMargin=inch,
                           leftMargin=inch,
                           topMargin=inch,
                           bottomMargin=inch)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Header
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=20
    )
    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=12,
        leading=16
    )
    
    # Add school header
    story.append(Paragraph("Question Paper", title_style))
    story.append(Paragraph(f"Subject: {subject} | Class: {class_num} | Chapter: {chapter}", subtitle_style))
    story.append(Paragraph("_" * 60, subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Add questions
    lines = questions.split('\n')
    for line in lines:
        if line.strip():
            # Clean any problematic characters
            clean_line = line.strip()
            story.append(Paragraph(clean_line, question_style))
            story.append(Spacer(1, 0.1*inch))
    
    doc.build(story)
    buffer.seek(0)
    
    # Send as downloadable PDF
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=question_paper_{subject}_class{class_num}.pdf'
    return response

if __name__ == "__main__":
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)