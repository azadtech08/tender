#!/usr/bin/env python3
"""
Generate PDF from DEPLOYMENT_GUIDE.md

Usage:
    pip install markdown2 pdfkit wkhtmltopdf
    python generate_deployment_pdf.py
"""

import os
import sys
from pathlib import Path

try:
    import markdown2
    import pdfkit
except ImportError:
    print("Installing required packages...")
    os.system("pip install markdown2 pdfkit")
    import markdown2
    import pdfkit


def generate_pdf():
    """Convert DEPLOYMENT_GUIDE.md to PDF"""
    
    # Paths
    md_file = Path(__file__).parent / "DEPLOYMENT_GUIDE.md"
    output_pdf = Path(__file__).parent / "DEPLOYMENT_GUIDE.pdf"
    
    if not md_file.exists():
        print(f"❌ Error: {md_file} not found")
        sys.exit(1)
    
    # Read markdown
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Convert markdown to HTML
    html_content = markdown2.markdown(
        md_content,
        extras=['tables', 'fenced-code-blocks', 'breaks']
    )
    
    # Add CSS for better PDF formatting
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>GeM Tender SaaS - Deployment Guide</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                margin: 20px;
                background-color: #f9f9f9;
            }}
            h1 {{
                color: #0066cc;
                border-bottom: 3px solid #0066cc;
                padding-bottom: 10px;
                page-break-after: avoid;
            }}
            h2 {{
                color: #0066cc;
                margin-top: 30px;
                page-break-after: avoid;
            }}
            h3 {{
                color: #333;
                page-break-after: avoid;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 15px 0;
                page-break-inside: avoid;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #0066cc;
                color: white;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }}
            pre {{
                background-color: #f4f4f4;
                padding: 12px;
                border-left: 4px solid #0066cc;
                overflow-x: auto;
                page-break-inside: avoid;
            }}
            ul, ol {{
                margin: 10px 0;
            }}
            li {{
                margin: 5px 0;
            }}
            .checklist {{
                background-color: #e8f4f8;
                padding: 15px;
                border-left: 4px solid #0066cc;
                margin: 15px 0;
            }}
            strong {{
                color: #0066cc;
            }}
            @page {{
                size: A4;
                margin: 1cm;
                @bottom-center {{
                    content: "Page " counter(page);
                }}
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # Check if wkhtmltopdf is installed
    try:
        pdfkit.from_string(html_template, str(output_pdf))
        print(f"✅ PDF generated successfully: {output_pdf}")
        return True
    except Exception as e:
        print(f"⚠️  Could not generate PDF with pdfkit: {e}")
        print("   Installing wkhtmltopdf...")
        
        # Try alternative: use markdown2 with html2pdf
        try:
            import weasyprint
            weasyprint.HTML(string=html_template).write_pdf(str(output_pdf))
            print(f"✅ PDF generated with WeasyPrint: {output_pdf}")
            return True
        except ImportError:
            print("⚠️  WeasyPrint not installed. Installing...")
            os.system("pip install weasyprint")
            try:
                import weasyprint
                weasyprint.HTML(string=html_template).write_pdf(str(output_pdf))
                print(f"✅ PDF generated successfully: {output_pdf}")
                return True
            except Exception as e2:
                print(f"❌ Failed to generate PDF: {e2}")
                print("\n💡 Alternative: Save the guide as PDF manually:")
                print(f"   1. Open {md_file} in VS Code")
                print("   2. Install 'Markdown PDF' extension")
                print("   3. Right-click → Markdown PDF: Export (pdf)")
                return False


if __name__ == "__main__":
    success = generate_pdf()
    sys.exit(0 if success else 1)
