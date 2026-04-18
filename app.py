from flask import Flask, render_template, request, make_response, session, redirect, url_for
from rag import generate_questions
import secrets
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import datetime, timedelta
import io
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))

# User database file
USERS_FILE = 'users.json'

def load_users():
    """Load user database from JSON file"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users_data):
    """Save user database to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users_data, f, indent=2)

# Rate limiting for anonymous users (IP-based)
ANONYMOUS_LIMIT = {}

def check_anonymous_limit(ip_address):
    """Check if anonymous user (no login) has used their 1 free paper"""
    now = datetime.now()
    
    # Clean up old entries (older than 24 hours)
    cleanup_time = now - timedelta(days=1)
    for ip in list(ANONYMOUS_LIMIT.keys()):
        if ANONYMOUS_LIMIT[ip]['reset_time'] < cleanup_time:
            del ANONYMOUS_LIMIT[ip]
    
    # Get or create IP entry
    if ip_address not in ANONYMOUS_LIMIT:
        ANONYMOUS_LIMIT[ip_address] = {
            'count': 0,
            'reset_time': now + timedelta(hours=1)
        }
    
    ip_data = ANONYMOUS_LIMIT[ip_address]
    
    # Reset counter if time has passed
    if now > ip_data['reset_time']:
        ip_data['count'] = 0
        ip_data['reset_time'] = now + timedelta(hours=1)
    
    # Check if used free paper
    if ip_data['count'] >= 1:
        return False, "🔒 Free paper used! Please signup to continue."
    
    return True, "✅ Free paper available (1/1)"

def check_user_limit(email):
    """Check if logged-in user has exceeded rate limits"""
    users = load_users()
    
    if email not in users:
        return False, "❌ User not found. Please signup."
    
    user = users[email]
    now = datetime.now()
    
    # Parse stored datetime strings
    hourly_reset = datetime.fromisoformat(user['hourly_reset'])
    daily_reset = datetime.fromisoformat(user['daily_reset'])
    
    # Reset hourly counter if time has passed
    if now > hourly_reset:
        user['hourly_count'] = 0
        user['hourly_reset'] = (now + timedelta(hours=1)).isoformat()
    
    # Reset daily counter if time has passed
    if now > daily_reset:
        user['daily_count'] = 0
        user['daily_reset'] = (now + timedelta(days=1)).isoformat()
    
    # Check limits
    if user['hourly_count'] >= 2:
        minutes_left = int((hourly_reset - now).total_seconds() / 60)
        return False, f"⏰ Hourly limit: 2 papers/hour. Try again in {minutes_left} minutes."
    
    if user['daily_count'] >= 5:
        hours_left = int((daily_reset - now).total_seconds() / 3600)
        return False, f"⏰ Daily limit: 5 papers/day. Try again in {hours_left} hours."
    
    # Increment counters
    user['hourly_count'] += 1
    user['daily_count'] += 1
    users[email] = user
    save_users(users)
    
    return True, f"✅ Used: {user['hourly_count']}/2 (hour), {user['daily_count']}/5 (day)"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/signup", methods=['GET', 'POST'])
def signup():
    """Signup page for new users"""
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        mobile = request.form.get('mobile', '').strip()
        email = request.form.get('email', '').strip()
        class_num = request.form.get('class_num', '').strip()
        
        # Validate required fields
        if not all([name, mobile, email, class_num]):
            return render_template("signup.html", 
                                 error="❌ All fields are required!")
        
        # Validate email format (simple check)
        if '@' not in email or '.' not in email:
            return render_template("signup.html",
                                 error="❌ Please enter a valid email address!")
        
        # Validate mobile (10 digits)
        if not mobile.isdigit() or len(mobile) != 10:
            return render_template("signup.html",
                                 error="❌ Mobile number must be 10 digits!")
        
        # Check if user already exists
        users = load_users()
        if email in users:
            # User exists, log them in
            session['user_email'] = email
            session['user_name'] = users[email]['name']
            return redirect(url_for('home'))
        
        # Create new user
        now = datetime.now()
        users[email] = {
            'name': name,
            'mobile': mobile,
            'email': email,
            'class': class_num,
            'created_at': now.isoformat(),
            'hourly_count': 0,
            'hourly_reset': (now + timedelta(hours=1)).isoformat(),
            'daily_count': 0,
            'daily_reset': (now + timedelta(days=1)).isoformat()
        }
        save_users(users)
        
        # Log user in
        session['user_email'] = email
        session['user_name'] = name
        
        print(f"✅ New user registered: {name} ({email})")
        return redirect(url_for('home'))
    
    # GET request - show signup form
    return render_template("signup.html")

@app.route("/logout")
def logout():
    """Logout current user"""
    session.clear()
    return redirect(url_for('home'))

@app.route("/generate", methods=["POST"])
def generate():
    try:
        # Get client IP address
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        
        # Check if user is logged in
        user_email = session.get('user_email')
        
        if user_email:
            # LOGGED-IN USER: Check user-specific limits (2/hour, 5/day)
            allowed, message = check_user_limit(user_email)
            if not allowed:
                return render_template("index.html", 
                                     questions=f"❌ {message}",
                                     subject="",
                                     class_num="",
                                     chapter="")
        else:
            # ANONYMOUS USER: Check if they've used their 1 free paper
            allowed, message = check_anonymous_limit(ip_address)
            if not allowed:
                # Redirect to signup page
                session['redirect_after_signup'] = True
                return redirect(url_for('signup'))
            
            # Mark free paper as used
            ANONYMOUS_LIMIT[ip_address]['count'] = 1
        
        # Log rate limit status
        print(f"📊 {message}")
        
        # Get form data
        subject = request.form.get("subject", "Mathematics")
        class_num = request.form.get("class_num", "8")
        chapter = request.form.get("chapter", "")
        num_q = request.form.get("num_questions", "10")
        difficulty = request.form.get("difficulty", "Medium")
        question_type = request.form.get("question_type", "Mixed")
        
        print(f"📊 Generating: {subject}, Class {class_num}, {chapter}, Type: {question_type}")
        
        # Generate questions
        result = generate_questions(subject, class_num, chapter, num_q, difficulty, question_type)
        
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)