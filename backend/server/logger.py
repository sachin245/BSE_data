import logging
import os

def get_app_logger(name: str, log_filename: str) -> logging.Logger:
    """
    Creates and returns a file-bound logger.
    """
    os.makedirs("logs", exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid adding multiple handlers if logger already exists
    if not logger.handlers:
        file_handler = logging.FileHandler(f"logs/{log_filename}", encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(name)s - [%(filename)s:%(lineno)d] - %(funcName)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        
    return logger

backend_logger = get_app_logger("backend", "backend.log")
streamlit_logger = get_app_logger("streamlit", "streamlit.log")
frontend_logger = get_app_logger("frontend", "frontend.log")
