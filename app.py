from flask import Flask, render_template, request, make_response, session
from rag import generate_questions
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import datetime, timedelta
import io
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

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

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    try:
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