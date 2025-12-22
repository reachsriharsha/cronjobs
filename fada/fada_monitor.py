#!/usr/bin/env python3
"""
FADA Press Release Monitor
Checks for new monthly vehicle retail data reports and generates AI summaries
"""

import os
import sys
import json
import re
import smtplib
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import requests
from bs4 import BeautifulSoup
import anthropic
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_URL = "https://fada.in"
PRESS_RELEASE_URL = f"{BASE_URL}/press-release-list.php"
STATE_FILE = Path.home() / ".fada_monitor_state.json"
DOWNLOAD_DIR = Path.home() / "fada_reports"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Email Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "myemail@gmail.com")

def load_state():
    """Load previously processed report URLs"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"processed_reports": []}

def save_state(state):
    """Save processed report URLs"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def fetch_press_releases():
    """Fetch and parse the press release page"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    try:
        response = requests.get(PRESS_RELEASE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching press releases: {e}")
        return None

def find_new_reports(html_content, processed_reports):
    """Find new vehicle retail data reports"""
    soup = BeautifulSoup(html_content, 'html.parser')
    new_reports = []
    
    # Look for links containing "Vehicle Retail Data" or "releases"
    # Pattern: "FADA releases November 2025 Vehicle Retail Data"
    pattern = re.compile(r'fada\s+releases.*vehicle\s+retail\s+data', re.IGNORECASE)
    
    # Strategy 1: Look for PDF links that contain the pattern in the href
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.endswith('.pdf') and pattern.search(href):
            # Extract title from the PDF filename
            pdf_name = href.split('/')[-1]
            # Remove the hash prefix and .pdf extension to get the title
            title_match = re.search(r'[a-f0-9]+(.+)\.pdf$', pdf_name, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
            else:
                title = pdf_name.replace('.pdf', '')
            
            # Make absolute URL if needed
            if not href.startswith('http'):
                href = f"{BASE_URL}/{href.lstrip('/')}"
            
            print(f"Found report link: {title} -> {href}")
            
            if href not in processed_reports:
                new_reports.append({
                    'title': title,
                    'url': href
                })
    
    # Strategy 2: Look for card containers with title and download button
    if not new_reports:
        for card in soup.find_all('div', class_='card-body'):
            # Find the title text
            title_elem = card.find(['h3', 'h4', 'h5'])
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                if pattern.search(title_text):
                    # Find the download link in the same card
                    download_link = card.find('a', href=lambda x: x and x.endswith('.pdf'))
                    if download_link:
                        href = download_link['href']
                        if not href.startswith('http'):
                            href = f"{BASE_URL}/{href.lstrip('/')}"
                        
                        print(f"Found report link: {title_text} -> {href}")
                        
                        if href not in processed_reports:
                            new_reports.append({
                                'title': title_text,
                                'url': href
                            })
    
    return new_reports

def download_pdf(url, filename):
    """Download PDF file"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        
        filepath = DOWNLOAD_DIR / filename
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        print(f"Downloaded: {filepath}")
        return filepath
    except requests.RequestException as e:
        print(f"Error downloading PDF: {e}")
        return None

def extract_pdf_text(pdf_path):
    """Extract text from PDF using pdfplumber"""
    try:
        import pdfplumber
        
        text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
        
        return "\n\n".join(text)
    except ImportError:
        print("pdfplumber not installed, trying pypdf...")
        return extract_pdf_text_pypdf(pdf_path)
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return None

def extract_pdf_text_pypdf(pdf_path):
    """Fallback: Extract text using pypdf"""
    try:
        from pypdf import PdfReader
        
        reader = PdfReader(pdf_path)
        text = []
        for page in reader.pages:
            text.append(page.extract_text())
        
        return "\n\n".join(text)
    except Exception as e:
        print(f"Error with pypdf extraction: {e}")
        return None

def generate_summary(text, report_title):
    """Generate AI summary using Claude"""
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set")
        return None
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""Analyze this FADA vehicle retail data report and provide a concise summary.

Report Title: {report_title}

Report Content:
{text[:50000]}  # Limit to avoid token overflow

Please provide:
1. Key highlights and main findings
2. Notable trends (growth/decline by category)
3. Important statistics
4. Any significant market insights

Keep the summary clear and actionable."""
            }]
        )
        
        return message.content[0].text
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None

def send_email(subject, body, to_email, attachment_path=None):
    """Send email notification with optional PDF attachment"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("Email not configured: SMTP_USER or SMTP_PASSWORD not set")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body
        msg.attach(MIMEText(body, 'plain'))
        
        # Add PDF attachment if provided
        if attachment_path and Path(attachment_path).exists():
            with open(attachment_path, 'rb') as f:
                pdf_attachment = MIMEApplication(f.read(), _subtype='pdf')
                pdf_attachment.add_header(
                    'Content-Disposition', 
                    'attachment', 
                    filename=Path(attachment_path).name
                )
                msg.attach(pdf_attachment)
        
        # Connect and send
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"Email sent successfully to {to_email}")
        return True
    
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_notification(report_title, summary, pdf_path):
    """Display summary and send email notification"""
    # Console output
    print("\n" + "="*80)
    print(f"NEW REPORT PROCESSED: {report_title}")
    print("="*80)
    print(f"\nReport saved to: {pdf_path}")
    print(f"\nSUMMARY:\n{summary}")
    print("\n" + "="*80)
    
    # Email notification
    email_subject = f"🚗 New FADA Report: {report_title}"
    email_body = f"""New FADA Vehicle Retail Data Report Available
{'='*50}

Report: {report_title}
Downloaded to: {pdf_path}

SUMMARY:
{summary}

{'='*50}
This is an automated notification from FADA Monitor.
"""
    
    send_email(email_subject, email_body, NOTIFICATION_EMAIL, pdf_path)

def main():
    """Main execution flow"""
    print(f"[{datetime.now()}] Starting FADA report monitor...")
    
    # Create download directory
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    # Load state
    state = load_state()
    processed = state["processed_reports"]
    
    # Fetch press releases
    html = fetch_press_releases()
    if not html:
        print("Failed to fetch press releases")
        sys.exit(1)
    
    # Find new reports
    new_reports = find_new_reports(html, processed)
    
    if not new_reports:
        print("No new reports found")
        sys.exit(0)
    
    print(f"Found {len(new_reports)} new report(s)")
    
    # Process each new report
    for report in new_reports:
        print(f"\nProcessing: {report['title']}")
        
        # Generate filename from title
        filename = re.sub(r'[^\w\s-]', '', report['title'])
        filename = re.sub(r'[\s]+', '_', filename)
        filename = f"{filename}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        # Download PDF
        pdf_path = download_pdf(report['url'], filename)
        if not pdf_path:
            continue
        
        # Extract text
        text = extract_pdf_text(pdf_path)
        if not text:
            print("Failed to extract PDF text")
            continue
        
        # Generate summary
        #summary = generate_summary(text, report['title'])
        #if not summary:
        #    print("Failed to generate summary")
        #    continue
        summary = "New report downloaded. Summary generation is currently disabled."
        # Send notification
        send_notification(report['title'], summary, pdf_path)
        
        # Mark as processed
        processed.append(report['url'])
    
    # Save state
    state["processed_reports"] = processed
    save_state(state)
    
    print(f"\n[{datetime.now()}] Monitor completed successfully")

if __name__ == "__main__":
    main()