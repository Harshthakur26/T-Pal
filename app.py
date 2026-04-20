# FORCE REBUILD - v2
#from supabase import create_client, Client

from supabase import create_client, Client
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

app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# User database file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
print(f"📁 Users file will be saved at: {USERS_FILE}")

# ============================================================================
# SUPABASE DATABASE OPERATIONS
# These functions interact with the Supabase backend database for user management
# ============================================================================

def get_user(email):
    """
    Fetch user from Supabase by email
    
    Args:
        email (str): User's email address to search for
    
    Returns:
        dict: User data if found, None otherwise
    """
    try:
        result = supabase.table("users").select("*").eq("email", email).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None

def create_user(user_data):
    """
    Create new user in Supabase
    
    Args:
        user_data (dict): User information (name, email, mobile, class, etc.)
    
    Returns:
        dict: Created user data if successful, None on failure
    """
    try:
        result = supabase.table("users").insert(user_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return None

def update_user(email, updates):
    """
    Update user fields in Supabase
    
    Args:
        email (str): User's email to identify who to update
        updates (dict): Dictionary of fields to update (hourly_count, daily_count, etc.)
    
    Returns:
        dict: Updated user data if successful, None on failure
    """
    try:
        result = supabase.table("users").update(updates).eq("email", email).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"❌ Error updating user: {e}")
        return None

# CHANGE 2: Update check_user_limit() Function
# (Adapted for Supabase instead of PostgreSQL/JSON)
# ============================================
def check_user_limit(email):
    """Check if logged-in user has exceeded rate limits
    
    NEW: Different limits for FREE vs PREMIUM users
    """
    user = get_user(email)  # Get from Supabase
    
    if not user:
        return False, "❌ User not found. Please signup."
    
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
    
    # ========== NEW: Different limits for FREE vs PREMIUM ==========
    is_premium = user.get('is_premium', False)
    
    if is_premium:
        # PREMIUM USERS: 2 papers/hour, 5 papers/day
        hourly_limit = 2
        daily_limit = 5
    else:
        # FREE USERS: 1 paper/hour, 1 paper/day
        hourly_limit = 1
        daily_limit = 1
    
    tier_name = "Premium" if is_premium else "Free"
    # ========== END DIFFERENT LIMITS ==========
    
    # Check limits
    if user['hourly_count'] >= hourly_limit:
        minutes_left = int((hourly_reset - now).total_seconds() / 60)
        return False, f"⏰ {tier_name} limit: {hourly_limit} papers/hour. Try again in {minutes_left} minutes."
    
    if user['daily_count'] >= daily_limit:
        hours_left = int((daily_reset - now).total_seconds() / 3600)
        return False, f"⏰ {tier_name} limit: {daily_limit} papers/day. Try again in {hours_left} hours."
    
    # Increment counters
    user['hourly_count'] += 1
    user['daily_count'] += 1
    
    # Update user in Supabase
    updates = {
        'hourly_count': user['hourly_count'],
        'daily_count': user['daily_count'],
        'hourly_reset': user['hourly_reset'],
        'daily_reset': user['daily_reset']
    }
    update_user(email, updates)
    
    return True, f"✅ {tier_name} user: {user['hourly_count']}/{hourly_limit} (hour), {user['daily_count']}/{daily_limit} (day)"

# Rate limiting for anonymous users (IP-based)
ANONYMOUS_LIMIT = {}
REQUESTS_PER_HOUR = 1  # Free tier: 4 papers per hour per IP
REQUESTS_PER_DAY = 2   # Free tier: 15 papers per day per IP


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
        
        # ====================================================================
        # CHECK IF USER ALREADY EXISTS IN SUPABASE
        # Queries Supabase to see if email is already registered
        # ====================================================================
        existing_user = get_user(email)
        if existing_user:
            # User exists in Supabase, log them in directly
            session['user_email'] = email
            session['user_name'] = existing_user['name']
            # CHANGE 4: Load Premium Status Into Session
            # ============================================
            session['user_premium'] = existing_user.get('is_premium', False)  # ← ADD THIS LINE
            print(f"✅ Returning user logged in: {existing_user['name']} ({email})")
            return redirect(url_for('home'))
        
        # ====================================================================
        # CREATE NEW USER IN SUPABASE
        # Stores user profile data and initializes rate limiting counters
        # All data is stored in cloud database, not JSON file
        # ====================================================================
        now = datetime.now()
        new_user = {
            "email": email,
            "name": name,
            "mobile": mobile,
            "class_teaching": class_num,
            # CHANGE 3: Update Signup to Add is_premium Field
            # ============================================
            'is_premium': False,  # ← ADD THIS LINE (new users start as FREE)
            "created_at": now.isoformat(),
            "hourly_count": 0,
            "hourly_reset": (now + timedelta(hours=1)).isoformat(),
            "daily_count": 0,
            "daily_reset": (now + timedelta(days=1)).isoformat()
        }
        created = create_user(new_user)
        
        if not created:
            return render_template("signup.html", error="❌ Signup failed. Please try again.")
        
        # ====================================================================
        # LOG NEW USER IN (Set session cookies)
        # Creates browser session to keep user logged in
        # ====================================================================
        session['user_email'] = email
        session['user_name'] = name
        # CHANGE 4: Load Premium Status Into Session
        # ============================================
        session['user_premium'] = False  # ← ADD THIS LINE (new users are FREE)
        
        print(f"✅ New user created and logged in: {name} ({email})")
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
        
        # ========== Load/Refresh Premium Status ==========
        if user_email:
            # Get fresh user data from Supabase
            user = get_user(user_email)
            if user:
                # Update session with current premium status
                session['user_premium'] = user.get('is_premium', False)
        
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
        
        # ========== PREMIUM FEATURE CHECK ==========
        # Check if user is trying to use premium features (>5 questions)
        user_email = session.get('user_email')
        is_premium = session.get('user_premium', False)
        
        # Convert num_q to integer
        try:
            num_questions = int(num_q)
        except:
            num_questions = 5
        
        # VALIDATION: Free users can ONLY generate 5 questions
        if not is_premium and num_questions > 5:
            # User is FREE but trying to generate >5 questions - BLOCK IT!
            return render_template("index.html",
                                 questions=f"""❌ <strong>Premium Feature Locked!</strong>
        
        <div style='background: #fff5f5; padding: 20px; border-radius: 10px; border-left: 4px solid #fc8181; margin: 20px 0;'>
            <p style='color: #c53030; font-size: 16px; margin-bottom: 10px;'>
                You're trying to generate <strong>{num_questions} questions</strong>, 
                but free users can only generate <strong>5 questions</strong>.
            </p>
        </div>
        
        <div style='background: #f0fff4; padding: 20px; border-radius: 10px; border-left: 4px solid #48bb78; margin: 20px 0;'>
            <h3 style='color: #22543d; margin-bottom: 10px;'>💎 Upgrade to Premium (₹300/month):</h3>
            <ul style='color: #2f855a; margin-left: 20px;'>
                <li>✅ Generate 10, 15, or 20 questions</li>
                <li>✅ 5 papers per day (vs 1 for free)</li>
                <li>✅ Priority support</li>
                <li>✅ All subjects & classes</li>
            </ul>
        </div>
        
        <div style='text-align: center; margin-top: 20px;'>
            <a href='/upgrade' style='display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                       color: white; padding: 15px 40px; border-radius: 10px; text-decoration: none; 
                                       font-weight: 700; font-size: 16px;'>
                Upgrade Now →
            </a>
        </div>
        """,
                                 subject=subject,
                                 class_num=class_num,
                                 chapter=chapter)
        
        print(f"✅ Premium check passed: User={user_email}, Premium={is_premium}, Questions={num_questions}")
        
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

# CHANGE 5: Add /upgrade Route
# ============================================
@app.route("/upgrade")
def upgrade():
    """Show premium upgrade page"""
    return render_template("upgrade.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)