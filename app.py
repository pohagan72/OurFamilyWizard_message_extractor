import os
import re
import zipfile
import tempfile
import shutil
import io
from flask import (
    Flask, request, render_template, send_file, flash, redirect, url_for
)
from werkzeug.utils import secure_filename
from pypdf import PdfReader, PdfWriter

# --- Configuration ---
# Use tempfile module for better temporary file management
# UPLOAD_FOLDER = 'temp_uploads'
# OUTPUT_FOLDER = 'temp_output'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_very_secret_and_random_key_123!' # Change this!
# Optional: Configure max upload size (e.g., 50MB)
# app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Modified PDF Splitting Function ---
def split_messages_pdf(input_pdf_path, output_dir):
    """
    Splits a PDF containing multiple messages into individual PDFs per message.

    Args:
        input_pdf_path (str): Path to the input PDF file.
        output_dir (str): Directory where the individual message PDFs will be saved.

    Returns:
        list: A list of paths to the generated PDF files, or None if an error occurs.
        str: An error message string if an error occurs, otherwise None.
    """
    # --- Setup Output Directory ---
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory for split files: '{output_dir}'")

    # --- Regex to find the message marker ---
    message_pattern = re.compile(r"Message\s+(\d+)\s+of\s+(\d+)")
    generated_files = []

    try:
        reader = PdfReader(input_pdf_path)
        num_pages = len(reader.pages)
        print(f"Processing '{os.path.basename(input_pdf_path)}' with {num_pages} pages...")

        current_message_number = 0
        total_messages_reported = 0
        pages_for_current_message = []

        # --- Process Pages ---
        for page_num in range(num_pages):
            page = reader.pages[page_num]
            try:
                text = page.extract_text()
                if not text:
                    print(f"Warning: Could not extract text from page {page_num + 1}. Assuming it belongs to the current message.")
                    if current_message_number > 0:
                         pages_for_current_message.append(page)
                    continue

                match = message_pattern.search(text)

                if match:
                    found_message_num = int(match.group(1))
                    found_total_messages = int(match.group(2))

                    if total_messages_reported == 0:
                         total_messages_reported = found_total_messages
                    elif total_messages_reported != found_total_messages:
                         print(f"Warning: Total message count changed from {total_messages_reported} to {found_total_messages} on page {page_num + 1}")
                         total_messages_reported = found_total_messages

                    if found_message_num != current_message_number:
                        if pages_for_current_message:
                            output_filename = f"message_{current_message_number}_of_{total_messages_reported}.pdf"
                            output_file_path = os.path.join(output_dir, output_filename)
                            writer = PdfWriter()
                            for msg_page in pages_for_current_message:
                                writer.add_page(msg_page)
                            with open(output_file_path, "wb") as outfile:
                                writer.write(outfile)
                            generated_files.append(output_file_path)
                            print(f"   Saved: {output_filename} ({len(pages_for_current_message)} pages)")

                        current_message_number = found_message_num
                        pages_for_current_message = [page]
                    else:
                         if page not in pages_for_current_message:
                             pages_for_current_message.append(page)
                else:
                    if current_message_number > 0:
                        pages_for_current_message.append(page)
                    else:
                        print(f"Skipping page {page_num + 1} (appears before first message marker)")

            except Exception as page_ex:
                print(f"Error processing page {page_num + 1}: {page_ex}")
                # Continue processing other pages if one fails
                continue

        # --- Save the VERY LAST message's pages ---
        if pages_for_current_message and current_message_number > 0:
             # Ensure total_messages_reported is set if only one message exists
            if total_messages_reported == 0 and match:
                total_messages_reported = int(match.group(2))
            elif total_messages_reported == 0:
                 print("Warning: Could not determine total message count for the last message.")
                 total_messages_reported = 'X' # Placeholder

            output_filename = f"message_{current_message_number}_of_{total_messages_reported}.pdf"
            output_file_path = os.path.join(output_dir, output_filename)
            writer = PdfWriter()
            for msg_page in pages_for_current_message:
                writer.add_page(msg_page)
            with open(output_file_path, "wb") as outfile:
                writer.write(outfile)
            generated_files.append(output_file_path)
            print(f"   Saved: {output_filename} ({len(pages_for_current_message)} pages)")

        if not generated_files:
            return [], "No messages found or extracted."

        return generated_files, None # Return list of files and no error

    except Exception as e:
        print(f"\nAn error occurred during PDF processing: {e}")
        import traceback
        traceback.print_exc()
        return None, f"An error occurred during PDF processing: {e}"

# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    """Renders the upload page."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handles file upload, splitting, zipping, and download."""
    if 'pdf_file' not in request.files:
        flash('No file part selected.')
        return redirect(request.url)

    file = request.files['pdf_file']

    if file.filename == '':
        flash('No file selected.')
        return redirect(request.url)

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        base_filename = os.path.splitext(original_filename)[0]

        # --- Use Temporary Directories ---
        temp_dir = None # Initialize to ensure cleanup happens
        try:
            temp_dir = tempfile.mkdtemp() # Main temporary directory for this request
            upload_path = os.path.join(temp_dir, original_filename)
            output_split_dir = os.path.join(temp_dir, 'output') # Subdir for split files

            print(f"Saving uploaded file temporarily to: {upload_path}")
            file.save(upload_path)

            # --- Split the PDF ---
            print(f"Splitting PDF: {upload_path}")
            split_files, error = split_messages_pdf(upload_path, output_split_dir)

            if error:
                flash(f'Error splitting PDF: {error}')
                return redirect(url_for('index'))

            if not split_files:
                flash('Could not find any messages matching the pattern "Message X of Y" in the PDF.')
                return redirect(url_for('index'))

            # --- Create ZIP in Memory ---
            print(f"Zipping {len(split_files)} split files...")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fpath in split_files:
                    arcname = os.path.basename(fpath) # Name inside the zip
                    print(f"  Adding to zip: {fpath} as {arcname}")
                    zf.write(fpath, arcname=arcname)

            zip_buffer.seek(0) # Rewind buffer to the beginning

            # --- Send ZIP File for Download ---
            zip_filename = f"{base_filename}_messages.zip"
            print(f"Sending zip file: {zip_filename}")
            return send_file(
                zip_buffer,
                as_attachment=True,
                download_name=zip_filename,
                mimetype='application/zip'
            )

        except Exception as e:
            print(f"An error occurred in the upload route: {e}")
            import traceback
            traceback.print_exc()
            flash(f'An unexpected error occurred: {e}')
            return redirect(url_for('index'))
        finally:
            # --- Cleanup Temporary Files/Directory ---
            if temp_dir and os.path.exists(temp_dir):
                print(f"Cleaning up temporary directory: {temp_dir}")
                try:
                    shutil.rmtree(temp_dir)
                    print("Temporary directory cleaned up successfully.")
                except Exception as cleanup_error:
                    print(f"Error cleaning up temporary directory {temp_dir}: {cleanup_error}")


    else:
        flash('Invalid file type. Please upload a PDF.')
        return redirect(request.url)

if __name__ == '__main__':
    # Make sure temporary directories don't conflict if running multiple instances
    # os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    app.run(debug=True) # debug=True is helpful for development, turn off for production
