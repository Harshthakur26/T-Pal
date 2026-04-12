import os
from groq import Groq
from pypdf import PdfReader

def read_pdfs(folder_path="data"):
    """Read all PDF files from the data folder"""
    all_text = ""
    
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".pdf"):
                filepath = os.path.join(root, file)
                try:
                    reader = PdfReader(filepath)
                    for page in reader.pages:
                        try:
                            text = page.extract_text()
                            if text:
                                all_text += text + "\n"
                        except Exception as e:
                            print(f"⚠️ Error reading page from {file}: {e}")
                except Exception as e:
                    print(f"⚠️ Error reading file {file}: {e}")
    
    print(f"Loaded PDF text: {len(all_text)} characters from {folder_path}")
    return all_text

# CODE ADDED: New function to read PDFs for specific subject and class
def read_pdfs_for_class(subject, class_num):
    """Read PDFs only for specific subject and class to avoid mixing content"""
    # CODE ADDED: Build the folder path based on subject and class number
    folder_path = f"data/{subject}/{class_num}"
    all_text = ""
    
    # CODE ADDED: Check if the folder exists before trying to read PDFs
    if not os.path.exists(folder_path):
        print(f"⚠️ Folder not found: {folder_path}")
        return all_text
    
    # CODE ADDED: Walk through the folder to find all PDF files
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".pdf"):
                filepath = os.path.join(root, file)
                try:
                    reader = PdfReader(filepath)
                    # CODE ADDED: Extract text from all pages in the PDF
                    for page in reader.pages:
                        try:
                            text = page.extract_text()
                            if text:
                                all_text += text + "\n"
                        except Exception as e:
                            print(f"⚠️ Error reading page from {file}: {e}")
                except Exception as e:
                    print(f"⚠️ Error reading file {file}: {e}")
    
    # CODE ADDED: Log the amount of content loaded for this subject and class
    print(f"Loaded {len(all_text)} characters for {subject} Class {class_num}")
    return all_text

# Load PDFs once when app starts
# print("Reading PDFs...")
# NCERT_TEXT = read_pdfs("data")
# print("PDFs loaded successfully!")

def find_relevant_context(subject, chapter, full_text, max_chars=5000):
    """Find relevant sections from the text based on chapter/subject
    
    FIX: Added strict subject filtering to prevent cross-contamination
    """
    # Simple keyword-based search for relevant content
    search_terms = chapter.lower().split()
    subject_terms = subject.lower().split()
    
    # CRITICAL FIX: Add subject-specific exclusion terms
    # Prevent Math content from appearing in Science and vice versa
    exclusion_terms = []
    if subject.lower() == "science":
        # Exclude math-specific terms when searching for Science
        exclusion_terms = [
            "equation", "solve for x", "linear equation", "quadratic",
            "polynomial", "algebra", "simplify", "calculate the value",
            "factorisation", "factorise", "algebraic expression"
        ]
    elif subject.lower() == "mathematics" or subject.lower() == "math":
        # Exclude pure science terms when searching for Math
        exclusion_terms = [
            "photosynthesis", "respiration", "cell", "tissue", "organism",
            "chemical reaction", "acid", "base", "ph", "reproduction",
            "microorganism", "crop", "synthetic fibres", "combustion"
        ]
    
    # Split text into chunks (roughly by paragraphs/sections)
    chunks = full_text.split('\n\n')
    
    # Score chunks by relevance
    scored_chunks = []
    for chunk in chunks:
        if len(chunk.strip()) < 50:  # Skip very short chunks
            continue
        
        chunk_lower = chunk.lower()
        
        # CRITICAL FIX: Check for exclusion terms first
        has_exclusion = False
        for exc_term in exclusion_terms:
            if exc_term in chunk_lower:
                has_exclusion = True
                break
        
        # Skip chunks with exclusion terms
        if has_exclusion:
            continue
        
        score = 0
        
        # Higher score for chunks containing search terms
        for term in search_terms:
            if term in chunk_lower:
                score += 10
        
        # Bonus for subject terms (but not as high)
        for term in subject_terms:
            if term in chunk_lower:
                score += 5
                
        if score > 0:
            scored_chunks.append((score, chunk))
    
    # Sort by score and take top chunks
    scored_chunks.sort(reverse=True, key=lambda x: x[0])
    
    # Combine top chunks until we reach max_chars
    relevant_text = ""
    for score, chunk in scored_chunks[:30]:  # Take top 30 relevant chunks
        if len(relevant_text) + len(chunk) > max_chars:
            break
        relevant_text += chunk + "\n\n"
    
    # If we didn't find enough relevant content, fall back to beginning
    if len(relevant_text) < 1000:
        print("⚠️ Limited relevant content found, using broader context")
        relevant_text = full_text[:max_chars]
    else:
        print(f"✅ Found {len(relevant_text)} characters of relevant context")
    
    return relevant_text

def validate_question_type(generated_text, expected_type):
    """Post-process to ensure questions match expected type"""
    lines = generated_text.strip().split('\n')
    filtered_lines = []
    
    if expected_type == "MCQ":
        # Keep only questions with options A), B), C), D) and Answer:
        in_mcq = False
        current_question = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line starts with Q or has options or Answer
            if line.startswith('Q') or line.startswith('**Q'):
                in_mcq = True
                current_question = [line]
            elif in_mcq:
                current_question.append(line)
                
                # Check if we have a complete MCQ
                if line.startswith('Answer:'):
                    # Verify it has options
                    has_options = any('A)' in l or 'B)' in l or 'C)' in l or 'D)' in l 
                                    for l in current_question)
                    if has_options:
                        filtered_lines.extend(current_question)
                        filtered_lines.append('')  # blank line
                    in_mcq = False
                    current_question = []
        
        result = '\n'.join(filtered_lines)
        if not result.strip():
            # If filtering removed everything, return original
            # (better to have mixed questions than nothing)
            return generated_text
        return result
    
    elif expected_type == "Short Answer":
        # Filter out MCQs (questions with A/B/C/D options)
        current_question = []
        is_mcq = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('Q'):
                if current_question and not is_mcq:
                    filtered_lines.extend(current_question)
                    filtered_lines.append('')
                current_question = [line]
                is_mcq = False
            else:
                current_question.append(line)
                # Check if it's an MCQ
                if any(line.startswith(opt) for opt in ['A)', 'B)', 'C)', 'D)']):
                    is_mcq = True
        
        # Add last question if it's not MCQ
        if current_question and not is_mcq:
            filtered_lines.extend(current_question)
        
        result = '\n'.join(filtered_lines)
        if not result.strip():
            return generated_text
        return result
    
    elif expected_type == "Long Answer":
        # Similar to Short Answer but keep longer responses
        return validate_question_type(generated_text, "Short Answer")
    
    elif expected_type == "Numerical":
        # NEW: Filter to keep only numerical/calculation problems
        # Look for mathematical symbols, equations, calculations
        current_question = []
        has_numbers = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('Q'):
                if current_question and has_numbers:
                    filtered_lines.extend(current_question)
                    filtered_lines.append('')
                current_question = [line]
                has_numbers = False
            else:
                current_question.append(line)
                # Check for numerical indicators
                if any(char in line for char in ['=', '+', '-', '×', '÷', '²', '³', '%']):
                    has_numbers = True
                # Check for numbers
                if any(char.isdigit() for char in line):
                    has_numbers = True
        
        # Add last question if it has numbers
        if current_question and has_numbers:
            filtered_lines.extend(current_question)
        
        result = '\n'.join(filtered_lines)
        if not result.strip():
            # For numerical, if filtering removed everything, 
            # return original (teacher feedback: need numericals!)
            return generated_text
        return result
    
    return generated_text

def generate_questions(subject, class_num, chapter, num_questions, difficulty, question_type="Mixed"):
    """Generate questions using Groq API with strict type enforcement
    
    NEW: Added "Numerical" question type for math problems
    FIX: Better subject filtering to prevent cross-contamination
    """
    
    print(f"\n{'='*60}")
    print(f"🎓 Generating {question_type} questions with Groq API...")
    print(f"{'='*60}")
    
    # Get API key from environment variable
    api_key = os.environ.get("GROQ_API_KEY")
    
    if not api_key:
        return """❌ ERROR: GROQ_API_KEY not found!
        
Please set your Groq API key:
1. Get free API key from: https://console.groq.com/keys
2. Set environment variable: GROQ_API_KEY=your_key_here

For local testing:
Windows: set GROQ_API_KEY=your_key_here
Mac/Linux: export GROQ_API_KEY=your_key_here

For Render deployment:
Add GROQ_API_KEY in Environment Variables section"""
    
    try:
        # Initialize Groq client
        client = Groq(api_key=api_key)
        
        # CODE ADDED: Load PDFs only for this specific subject and class
        print(f"📚 Loading PDFs for {subject} Class {class_num}...")
        pdf_text = read_pdfs_for_class(subject, class_num)
        
        # CODE ADDED: Fallback mechanism if specific folder not found
        if not pdf_text:
            print(f"⚠️ No PDFs found for {subject} Class {class_num}, trying alternative approach")
            # Try loading from all data if specific class folder doesn't exist
            pdf_text = read_pdfs("data")
        
        # CODE ADDED: Now use the loaded pdf_text instead of global NCERT_TEXT
        print(f"📚 Searching for relevant {subject} content about '{chapter}'...")
        relevant_context = find_relevant_context(subject, chapter, pdf_text, max_chars=5000)
        
        # Build STRICT system message and prompt based on question type
        if question_type == "MCQ":
            system_message = """You are an expert NCERT question paper creator. You ONLY create Multiple Choice Questions (MCQs).

CRITICAL RULES:
1. EVERY question MUST have exactly 4 options: A), B), C), D)
2. EVERY question MUST have "Answer: X" where X is A, B, C, or D
3. DO NOT create any short answer or long answer questions
4. DO NOT create questions without options
5. Format MUST be strictly followed"""
            
            format_instruction = """Generate ONLY Multiple Choice Questions in this EXACT format:

Q1. [Question text here]
A) [option 1]
B) [option 2]
C) [option 3]
D) [option 4]
Answer: [A/B/C/D]

Q2. [Question text here]
A) [option 1]
B) [option 2]
C) [option 3]
D) [option 4]
Answer: [A/B/C/D]

IMPORTANT: Do NOT create any questions without A/B/C/D options. Every single question MUST be a multiple choice question."""
        
        elif question_type == "Short Answer":
            system_message = """You are an expert NCERT question paper creator. You ONLY create Short Answer questions (1-2 sentence answers).

CRITICAL RULES:
1. Questions should require 1-2 sentence answers
2. DO NOT create MCQs with options A/B/C/D
3. DO NOT create long detailed questions
4. Answers should be brief and direct"""
            
            format_instruction = """Generate ONLY Short Answer questions in this EXACT format:

Q1. [Question requiring 1-2 sentence answer]
Answer: [Brief 1-2 sentence answer]

Q2. [Question requiring 1-2 sentence answer]
Answer: [Brief 1-2 sentence answer]

IMPORTANT: Do NOT include any multiple choice options (A/B/C/D). All questions must be short answer type."""
        
        elif question_type == "Long Answer":
            system_message = """You are an expert NCERT question paper creator. You ONLY create Long Answer questions (detailed 3-5 sentence answers or step-by-step solutions).

CRITICAL RULES:
1. Questions should require detailed explanations or step-by-step solutions
2. DO NOT create MCQs with options A/B/C/D
3. Answers should be comprehensive (3-5 sentences or multiple steps)
4. Good for "Explain", "Prove", "Derive", "Solve" type questions"""
            
            format_instruction = """Generate ONLY Long Answer questions in this EXACT format:

Q1. [Question requiring detailed explanation or step-by-step solution]
Answer: [Detailed answer with 3-5 sentences or clear steps]

Q2. [Question requiring detailed explanation or step-by-step solution]  
Answer: [Detailed answer with 3-5 sentences or clear steps]

IMPORTANT: Do NOT include any multiple choice options (A/B/C/D). All questions must require detailed answers."""
        
        elif question_type == "Numerical":
            # NEW: Numerical problem type for Math (and Science calculations)
            system_message = """You are an expert NCERT question paper creator specializing in NUMERICAL PROBLEMS.

CRITICAL RULES:
1. EVERY question MUST involve calculations, numbers, or mathematical operations
2. Questions should require solving, computing, or calculating numerical values
3. Include step-by-step solutions showing all calculations
4. Use proper mathematical notation (=, +, -, ×, ÷, etc.)
5. DO NOT create theoretical or definition-based questions
6. DO NOT create MCQs with options A/B/C/D
7. Focus on: Solve, Calculate, Find, Compute, Determine"""
            
            if subject.lower() in ["mathematics", "math", "maths"]:
                # CODE ADDED: Simplified format for generating numerical problems with concise answers
                format_instruction = """Generate ONLY NUMERICAL PROBLEMS with concise answers:

Q1. [Numerical problem]
Answer: [numeric value with unit]

Q2. [Numerical problem]
Answer: [numeric value with unit]

# CODE ADDED: Important guidelines for numerical problem generation
IMPORTANT: 
- Keep answers short (just the number and unit)
- No step-by-step explanation needed
- Focus on calculation-based questions"""
            else:  # Science
                format_instruction = """Generate ONLY NUMERICAL PROBLEMS for Science in this EXACT format:

Q1. Calculate: [Numerical problem related to Science concept]
Answer:
Step 1: [Calculation or explanation]
Step 2: [Calculation]
Final Answer: [Numerical result with units]

EXAMPLES FOR SCIENCE:
- Calculate the speed if distance is 100m and time is 5s
- If a force of 10N is applied over an area of 2m², calculate the pressure
- Calculate the percentage of oxygen in air if it is 21 parts per 100

IMPORTANT:
- Include numbers and calculations
- Relate to Science concepts (force, pressure, speed, etc.)
- Show working/steps
- Include units in answers"""
        
        else:  # Mixed
            system_message = "You are an expert NCERT question paper creator. You create a mix of MCQs, short answer, and long answer questions."
            
            format_instruction = """Generate a MIX of question types:
- Some MCQs (with A/B/C/D options and Answer: X)
- Some Short Answer (brief 1-2 sentence answers)
- Some Long Answer (detailed 3-5 sentence answers)

Format examples shown above."""
        
        # Create main prompt with STRICT subject reinforcement
        prompt = f"""You are creating a Class {class_num} {subject} question paper on "{chapter}".

CRITICAL: This is for {subject} ONLY. Do NOT include questions from other subjects.

Use this NCERT {subject} content as reference:

{relevant_context}

TASK:
Generate EXACTLY {num_questions} {subject} questions at {difficulty} difficulty level.

{format_instruction}

QUALITY REQUIREMENTS:
1. Questions must be based STRICTLY on {subject} content (NOT other subjects!)
2. Questions must be from the chapter "{chapter}" in Class {class_num} {subject}
3. Difficulty level: {difficulty} - adjust complexity accordingly
4. Questions should test understanding, not just memory
5. Use proper terminology from NCERT {subject} textbooks
6. Make questions clear and unambiguous
7. Ensure answers are accurate based on NCERT content

IMPORTANT: Only create {subject} questions. Do not mix with other subjects!

Generate the {num_questions} {subject} questions with answers now:"""

        print(f"🤖 Sending request to Groq API...")
        print(f"   Model: llama-3.3-70b-versatile")
        print(f"   Subject: {subject}")
        print(f"   Type: {question_type}")
        print(f"   Prompt length: {len(prompt)} characters")
        
        # Call Groq API with strict system message
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.5,  # Lower temperature for more consistent formatting
            max_tokens=2500,
            top_p=0.9,
            stream=False
        )
        
        # Extract generated text
        generated_text = chat_completion.choices[0].message.content
        
        print(f"✅ Generation complete! ({len(generated_text)} characters)")
        
        # Post-process to validate question type (extra safety)
        if question_type in ["MCQ", "Short Answer", "Long Answer", "Numerical"]:
            generated_text = validate_question_type(generated_text, question_type)
        
        print(f"{'='*60}\n")
        
        if not generated_text.strip():
            return "❌ ERROR: Groq returned empty response. Try again."
        
        return generated_text
        
    except Exception as e:
        print(f"❌ Error calling Groq API: {e}")
        import traceback
        traceback.print_exc()
        
        error_msg = str(e)
        
        # Handle common errors
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            return """❌ ERROR: Invalid Groq API Key

Please check:
1. Your API key is correct
2. API key is set in environment variables
3. Get a new key from: https://console.groq.com/keys"""
        
        elif "rate limit" in error_msg.lower():
            return """❌ ERROR: Groq API Rate Limit Exceeded

Groq free tier limits:
- 30 requests per minute
- 14,400 requests per day

Please wait a moment and try again."""
        
        else:
            return f"❌ ERROR: {type(e).__name__}: {str(e)}\n\nPlease try again or contact support."