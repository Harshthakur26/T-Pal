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

# Load PDFs once when app starts
print("Reading PDFs...")
NCERT_TEXT = read_pdfs("data")
print("PDFs loaded successfully!")

def find_relevant_context(subject, chapter, full_text, max_chars=5000):
    """Find relevant sections from the text based on chapter/subject"""
    # Simple keyword-based search for relevant content
    search_terms = chapter.lower().split()
    subject_terms = subject.lower().split()
    
    # Split text into chunks (roughly by paragraphs/sections)
    chunks = full_text.split('\n\n')
    
    # Score chunks by relevance
    scored_chunks = []
    for chunk in chunks:
        if len(chunk.strip()) < 50:  # Skip very short chunks
            continue
        
        chunk_lower = chunk.lower()
        score = 0
        
        # Higher score for chunks containing search terms
        for term in search_terms:
            if term in chunk_lower:
                score += 10
        
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
            elif in_mcq and any(opt in line for opt in ['A)', 'B)', 'C)', 'D)', 'Answer:']):
                current_question.append(line)
                # If we found Answer:, add this question
                if 'Answer:' in line:
                    filtered_lines.extend(current_question)
                    filtered_lines.append('')
                    in_mcq = False
            elif in_mcq:
                current_question.append(line)
    
    elif expected_type == "Short Answer":
        # Keep only questions with short answers (no options A/B/C/D)
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                filtered_lines.append('')
                continue
            
            # Skip lines with MCQ options
            if any(opt in line for opt in ['A)', 'B)', 'C)', 'D)']) and not line.startswith('Answer:'):
                continue
            
            filtered_lines.append(line)
    
    elif expected_type == "Long Answer":
        # Keep questions with detailed answers (no MCQ options)
        for line in lines:
            line = line.strip()
            if not line:
                filtered_lines.append('')
                continue
            
            # Skip lines with MCQ options
            if any(opt in line for opt in ['A)', 'B)', 'C)', 'D)']) and not line.startswith('Answer:'):
                continue
            
            filtered_lines.append(line)
    
    else:  # Mixed - keep everything
        return generated_text
    
    result = '\n'.join(filtered_lines)
    
    # If filtering removed too much, return original with warning
    if len(result.strip()) < 100:
        print(f"⚠️ Filtering removed too much content. Returning original.")
        return generated_text
    
    print(f"✅ Filtered to {expected_type} format")
    return result

def generate_questions(subject, class_num, chapter, num_questions, difficulty, question_type="Mixed"):
    """Generate questions using Groq API with strict type enforcement"""
    
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
        
        # Get relevant context from PDFs
        print(f"📚 Searching for relevant content about '{chapter}'...")
        relevant_context = find_relevant_context(subject, chapter, NCERT_TEXT, max_chars=5000)
        
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
        
        else:  # Mixed
            system_message = "You are an expert NCERT question paper creator. You create a mix of MCQs, short answer, and long answer questions."
            
            format_instruction = """Generate a MIX of question types:
- Some MCQs (with A/B/C/D options and Answer: X)
- Some Short Answer (brief 1-2 sentence answers)
- Some Long Answer (detailed 3-5 sentence answers)

Format examples shown above."""
        
        # Create main prompt
        prompt = f"""You are creating a Class {class_num} {subject} question paper on "{chapter}".

Use this NCERT content as reference:

{relevant_context}

TASK:
Generate EXACTLY {num_questions} questions at {difficulty} difficulty level.

{format_instruction}

QUALITY REQUIREMENTS:
1. Questions must be based on the NCERT content provided above
2. Difficulty level: {difficulty} - adjust complexity accordingly
3. Questions should test understanding, not just memory
4. Use proper terminology from NCERT textbooks
5. Make questions clear and unambiguous
6. Ensure answers are accurate based on NCERT content

Generate the {num_questions} questions with answers now:"""

        print(f"🤖 Sending request to Groq API...")
        print(f"   Model: llama-3.3-70b-versatile")
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
        if question_type in ["MCQ", "Short Answer", "Long Answer"]:
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