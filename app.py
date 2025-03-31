# -*- coding: utf-8 -*-
"""
Flask web application to split a multi-message PDF file based on markers.

This application allows users to upload a PDF file containing multiple messages,
typically marked with a pattern like "Message X of Y". It processes the PDF,
splits it into individual PDF files (one per message), zips these files,
and provides the zip archive for download. It uses temporary directories for
intermediate file storage and cleans them up after processing.
"""

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

# Allowed file extensions for upload. Prevents upload of non-PDF files.
ALLOWED_EXTENSIONS = {'pdf'}

# Initialize the Flask application instance.
app = Flask(__name__)

# WARNING: SECRET_KEY should NOT be hardcoded, especially in public code.
# It's crucial for session security. Load from environment variables or a
# secure configuration file in production.
app.config['SECRET_KEY'] = 'your_very_secret_and_random_key_123!' # Change this!

# Optional: Configure max upload size to prevent Denial-of-Service via large uploads.
# Example: 50MB limit. Uncomment and adjust as needed for your environment.
# app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# --- Helper Functions ---

def allowed_file(filename):
    """
    Checks if the uploaded file's extension is permitted.

    Args:
        filename (str): The name of the file uploaded by the user.

    Returns:
        bool: True if the file extension is in ALLOWED_EXTENSIONS, False otherwise.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- PDF Splitting Function ---

def split_messages_pdf(input_pdf_path, output_dir):
    """
    Splits a PDF containing multiple messages into individual PDFs per message.

    It searches each page's text for a pattern "Message X of Y" to identify
    the start of a new message and determine the total count. Pages between
    markers (or after the last marker) are grouped into separate output PDFs.

    Args:
        input_pdf_path (str): Path to the input PDF file to be processed.
        output_dir (str): Directory where the individual message PDF files
                          will be saved.

    Returns:
        tuple: A tuple containing:
            - list: A list of paths to the generated PDF files. Returns an empty
                    list if no messages are found or an error occurs during
                    initialization.
            - str or None: An error message string if a significant error occurs
                           during processing, otherwise None. Returns a specific
                           message if no messages matching the pattern are found.
    """
    # Ensure the output directory exists.
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory for split files: '{output_dir}'")

    # Regex to find the message marker (e.g., "Message 1 of 10").
    # Captures the current message number (group 1) and total messages (group 2).
    message_pattern = re.compile(r"Message\s+(\d+)\s+of\s+(\d+)")

    # List to store the paths of the generated PDF files.
    generated_files = []

    try:
        # Open the input PDF file for reading.
        reader = PdfReader(input_pdf_path)
        num_pages = len(reader.pages)
        print(f"Processing '{os.path.basename(input_pdf_path)}' with {num_pages} pages...")

        # --- State variables for tracking messages during page iteration ---
        current_message_number = 0 # Tracks the message number being currently processed.
        total_messages_reported = 0 # Stores the total number of messages reported in the markers.
        pages_for_current_message = [] # Accumulates PageObjects for the current message.
        last_match = None # Store the last regex match object

        # --- Iterate through each page of the PDF ---
        for page_num in range(num_pages):
            page = reader.pages[page_num]
            try:
                # Attempt to extract text from the current page.
                text = page.extract_text()
                if not text:
                    # Handle pages where text extraction fails (e.g., image-only pages).
                    # Assume such pages belong to the currently active message.
                    print(f"Warning: Could not extract text from page {page_num + 1}. Assuming it belongs to the current message.")
                    if current_message_number > 0: # Only add if a message has started
                         pages_for_current_message.append(page)
                    continue # Move to the next page

                # Search for the message marker pattern in the extracted text.
                match = message_pattern.search(text)

                if match:
                    # A message marker was found on this page.
                    found_message_num = int(match.group(1))
                    found_total_messages = int(match.group(2))
                    last_match = match # Store the latest match

                    # Initialize or verify the total message count.
                    if total_messages_reported == 0:
                         total_messages_reported = found_total_messages
                    elif total_messages_reported != found_total_messages:
                         # Log a warning if the total count changes mid-document.
                         print(f"Warning: Total message count changed from {total_messages_reported} to {found_total_messages} on page {page_num + 1}")
                         total_messages_reported = found_total_messages # Update to the latest reported count

                    # Check if this marker indicates the start of a *new* message.
                    if found_message_num != current_message_number:
                        # If we have accumulated pages for the *previous* message, write them to a file.
                        if pages_for_current_message:
                            # Construct the output filename.
                            output_filename = f"message_{current_message_number}_of_{total_messages_reported}.pdf"
                            output_file_path = os.path.join(output_dir, output_filename)

                            # Create a PdfWriter instance and add the collected pages.
                            writer = PdfWriter()
                            for msg_page in pages_for_current_message:
                                writer.add_page(msg_page)

                            # Write the new PDF file.
                            with open(output_file_path, "wb") as outfile:
                                writer.write(outfile)
                            generated_files.append(output_file_path)
                            print(f"   Saved: {output_filename} ({len(pages_for_current_message)} pages)")

                        # Start accumulating pages for the newly found message.
                        current_message_number = found_message_num
                        pages_for_current_message = [page] # Start list with the current page
                    else:
                        # This page contains the *same* message marker as the previous one found.
                        # Add the page to the current message's list if not already added (unlikely but safe).
                         if page not in pages_for_current_message:
                             pages_for_current_message.append(page)
                else:
                    # No message marker found on this page.
                    if current_message_number > 0:
                        # If we are already tracking a message, append this page to it.
                        pages_for_current_message.append(page)
                    else:
                        # This page appears before the very first message marker. Skip it.
                        print(f"Skipping page {page_num + 1} (appears before first message marker)")

            except Exception as page_ex:
                # Handle errors during processing of a single page.
                print(f"Error processing page {page_num + 1}: {page_ex}")
                # Continue processing the rest of the PDF.
                continue

        # --- After the loop: Save the pages for the very last message ---
        if pages_for_current_message and current_message_number > 0:
            # Ensure total_messages_reported is sensible even if the last page didn't have a clear marker
            # (e.g., if the very last message only had one page which had the marker).
            if total_messages_reported == 0 and last_match:
                total_messages_reported = int(last_match.group(2))
            elif total_messages_reported == 0:
                 print("Warning: Could not determine total message count for the last message.")
                 total_messages_reported = 'X' # Use a placeholder if count is unknown

            # Construct filename and path for the last message.
            output_filename = f"message_{current_message_number}_of_{total_messages_reported}.pdf"
            output_file_path = os.path.join(output_dir, output_filename)

            # Create PdfWriter, add pages, and write the file.
            writer = PdfWriter()
            for msg_page in pages_for_current_message:
                writer.add_page(msg_page)
            with open(output_file_path, "wb") as outfile:
                writer.write(outfile)
            generated_files.append(output_file_path)
            print(f"   Saved: {output_filename} ({len(pages_for_current_message)} pages)")

        # --- Final checks and return ---
        if not generated_files:
            # If no files were created, it means no markers were found.
            return [], "No messages found matching the pattern 'Message X of Y'."

        # Successfully processed, return the list of generated file paths.
        return generated_files, None

    except Exception as e:
        # Handle major errors during PDF processing (e.g., file corruption, library issues).
        print(f"\nAn error occurred during PDF processing: {e}")
        import traceback
        traceback.print_exc() # Log detailed traceback to server console
        # Return an empty list and the error message for flashing to the user.
        return [], f"An error occurred during PDF processing: {e}"

# --- Flask Routes ---

@app.route('/', methods=['GET'])
def index():
    """
    Renders the main HTML page with the file upload form.
    Handles GET requests to the root URL.
    """
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handles the file upload via POST request.
    Performs validation, saves the uploaded file temporarily, calls the PDF
    splitting function, zips the results, and sends the zip file for download.
    Includes error handling and cleanup of temporary files.
    """
    # --- 1. Validate Request ---
    # Check if the POST request has the 'pdf_file' part.
    if 'pdf_file' not in request.files:
        flash('No file part selected.')
        return redirect(request.url) # Redirect back to the upload form

    file = request.files['pdf_file']

    # Check if the user selected a file. The browser might send an empty
    # file part if no file was selected.
    if file.filename == '':
        flash('No file selected.')
        return redirect(request.url)

    # --- 2. Process Valid File ---
    if file and allowed_file(file.filename):
        # Sanitize the filename to prevent directory traversal issues.
        original_filename = secure_filename(file.filename)
        # Get the base name for naming the output zip file.
        base_filename = os.path.splitext(original_filename)[0]

        # --- Use Temporary Directories for Safety and Cleanup ---
        temp_dir = None # Initialize to ensure cleanup block works even if mkdtemp fails
        try:
            # Create a unique temporary directory for this request's files.
            # This prevents conflicts between concurrent requests and aids cleanup.
            temp_dir = tempfile.mkdtemp()
            upload_path = os.path.join(temp_dir, original_filename)
            # Create a subdirectory within the temp dir for split PDF files.
            output_split_dir = os.path.join(temp_dir, 'output')

            # --- 3. Save Uploaded File Temporarily ---
            print(f"Saving uploaded file temporarily to: {upload_path}")
            file.save(upload_path)

            # --- 4. Split the PDF ---
            print(f"Splitting PDF: {upload_path}")
            split_files, error = split_messages_pdf(upload_path, output_split_dir)

            # Handle errors reported by the splitting function.
            if error:
                flash(f'Error splitting PDF: {error}') # Display the error to the user
                # Note: Consider logging the full error server-side and showing a generic user message.
                return redirect(url_for('index'))

            # Handle case where splitting succeeded but found no messages.
            if not split_files:
                # This case is now handled by the 'error' variable check above based on split_messages_pdf return
                # flash('Could not find any messages matching the pattern "Message X of Y" in the PDF.')
                # return redirect(url_for('index'))
                # Kept comment for clarity, but logic moved. If split_files is empty and error is None,
                # the zip creation below will handle it gracefully (empty zip).
                # Let's refine the check based on the improved return value:
                 if not split_files and not error: # Check if function returned empty list AND no error string
                     flash('Splitting process completed, but no messages matching the pattern "Message X of Y" were found.')
                     return redirect(url_for('index'))


            # --- 5. Create ZIP Archive in Memory ---
            print(f"Zipping {len(split_files)} split files...")
            # Use an in-memory bytes buffer to avoid writing the zip file to disk.
            zip_buffer = io.BytesIO()
            # Create a ZipFile object operating on the buffer.
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add each generated PDF file to the zip archive.
                for fpath in split_files:
                    arcname = os.path.basename(fpath) # Use the file's base name as its name inside the zip.
                    print(f"  Adding to zip: {fpath} as {arcname}")
                    zf.write(fpath, arcname=arcname)

            # Reset the buffer's position to the beginning for reading.
            zip_buffer.seek(0)

            # --- 6. Send ZIP File for Download ---
            zip_filename = f"{base_filename}_messages.zip"
            print(f"Sending zip file: {zip_filename}")
            # Use send_file to send the contents of the memory buffer as a downloadable file.
            return send_file(
                zip_buffer,
                as_attachment=True, # Send as attachment to prompt download.
                download_name=zip_filename, # Suggest a filename to the browser.
                mimetype='application/zip' # Set the correct MIME type.
            )

        except Exception as e:
            # Catch any unexpected errors during the upload/processing/zipping.
            print(f"An error occurred in the upload route: {e}")
            import traceback
            traceback.print_exc() # Log the full traceback for debugging.
            # Provide a generic error message to the user.
            flash(f'An unexpected error occurred: {e}') # Consider more generic message for production.
            return redirect(url_for('index'))

        finally:
            # --- 7. Cleanup: ALWAYS remove the temporary directory and its contents ---
            # This block executes whether the try block succeeded or failed.
            if temp_dir and os.path.exists(temp_dir):
                print(f"Cleaning up temporary directory: {temp_dir}")
                try:
                    shutil.rmtree(temp_dir) # Recursively delete the directory.
                    print("Temporary directory cleaned up successfully.")
                except Exception as cleanup_error:
                    # Log errors during cleanup, but don't interrupt the user flow.
                    print(f"Error cleaning up temporary directory {temp_dir}: {cleanup_error}")
                    # Consider using app.logger for production logging.

    else:
        # Handle invalid file type uploads.
        flash('Invalid file type. Please upload a PDF.')
        return redirect(request.url)

# --- Main Execution Block ---

if __name__ == '__main__':
    # This block runs only when the script is executed directly (not imported).
    # It's typically used for starting the Flask development server.

    # WARNING: debug=True enables the Werkzeug debugger and auto-reloader.
    # This is useful for development but EXTREMELY DANGEROUS in production.
    # It allows arbitrary code execution if an error occurs.
    # Set debug=False or remove it entirely when deploying.
    # Use a proper WSGI server (like Gunicorn or uWSGI) for deployment instead of app.run().
    app.run(debug=True)
