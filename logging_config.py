import logging
import sys

# Configure root logger to output to console
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear any existing handlers to avoid duplicates
if root_logger.handlers:
    root_logger.handlers.clear()

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# Add file handler
file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

# Create a logger specifically for the application
app_logger = logging.getLogger('streamlit_app')
app_logger.setLevel(logging.INFO)
