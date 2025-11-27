import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger("database")

# Database file path - in src folder
DB_PATH = Path(__file__).parent / "fraud_cases.db"


def get_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


def init_database():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fraud_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userName TEXT NOT NULL,
            securityIdentifier TEXT NOT NULL,
            cardEnding TEXT NOT NULL,
            caseStatus TEXT NOT NULL,
            transactionName TEXT NOT NULL,
            transactionAmount REAL NOT NULL,
            transactionTime TEXT NOT NULL,
            transactionCategory TEXT NOT NULL,
            transactionSource TEXT NOT NULL,
            transactionLocation TEXT NOT NULL,
            securityQuestion TEXT NOT NULL,
            securityAnswer TEXT NOT NULL,
            outcome TEXT,
            lastUpdated TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")


def get_fraud_case_by_username(username: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a pending fraud case for a specific user.
    
    Args:
        username: The user's name
        
    Returns:
        Dictionary containing fraud case details or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Normalize the input username - remove spaces and convert to lowercase
    normalized_input = username.lower().replace(" ", "").replace("-", "")
    
    # Get all pending cases
    cursor.execute('''
        SELECT * FROM fraud_cases 
        WHERE caseStatus = 'pending_review'
    ''')
    
    cases = cursor.fetchall()
    conn.close()
    
    # Find matching case with normalized username comparison
    for case in cases:
        if case["userName"]:
            # Normalize the stored username as well
            normalized_stored = case["userName"].lower().replace(" ", "").replace("-", "")
            
            # Match if normalized names are the same
            if normalized_stored == normalized_input:
                return dict(case)
    
    return None


def verify_security_identifier(username: str, identifier: str) -> bool:
    """
    Verify the security identifier for a user.
    
    Args:
        username: The user's name
        identifier: The security identifier to verify
        
    Returns:
        True if identifier matches, False otherwise
    """
    case = get_fraud_case_by_username(username)
    if case:
        return case["securityIdentifier"] == identifier
    return False


def verify_security_answer(username: str, answer: str) -> bool:
    """
    Verify the security question answer for a user.
    
    Args:
        username: The user's name
        answer: The security answer to verify
        
    Returns:
        True if answer matches (case-insensitive), False otherwise
    """
    case = get_fraud_case_by_username(username)
    if case and case["securityAnswer"]:
        return case["securityAnswer"].lower() == answer.lower().strip()
    return False


def update_fraud_case_status(username: str, status: str, outcome: str) -> bool:
    """
    Update the fraud case status and outcome for a user.
    
    Args:
        username: The user's name (exact match from database)
        status: New status (e.g., 'confirmed_safe', 'confirmed_fraud', 'verification_failed')
        outcome: Description of the outcome
        
    Returns:
        True if update successful, False otherwise
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now().isoformat()
        
        # Log the update attempt
        logger.info(f"Attempting to update case for username='{username}', status='{status}'")
        
        cursor.execute('''
            UPDATE fraud_cases 
            SET caseStatus = ?, outcome = ?, lastUpdated = ?
            WHERE userName = ? AND caseStatus = 'pending_review'
        ''', (status, outcome, current_time, username))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if updated:
            logger.info(f"Successfully updated fraud case for {username}: {status} - {outcome}")
            return True
        else:
            logger.warning(f"No pending fraud case found for username='{username}'. Check if case exists and is pending.")
            return False
    except Exception as e:
        logger.error(f"Error updating fraud case for {username}: {e}")
        return False


def get_all_cases() -> List[Dict[str, Any]]:
    """
    Retrieve all fraud cases from the database.
    
    Returns:
        List of dictionaries containing fraud case details
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM fraud_cases')
    cases = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return cases


def insert_fraud_case(case: Dict[str, Any]) -> bool:
    """
    Insert a new fraud case into the database.
    
    Args:
        case: Dictionary containing fraud case details
        
    Returns:
        True if insert successful, False otherwise
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO fraud_cases (
                userName, securityIdentifier, cardEnding, caseStatus,
                transactionName, transactionAmount, transactionTime,
                transactionCategory, transactionSource, transactionLocation,
                securityQuestion, securityAnswer, outcome, lastUpdated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            case.get("userName"),
            case.get("securityIdentifier"),
            case.get("cardEnding"),
            case.get("caseStatus"),
            case.get("transactionName"),
            case.get("transactionAmount"),
            case.get("transactionTime"),
            case.get("transactionCategory"),
            case.get("transactionSource"),
            case.get("transactionLocation"),
            case.get("securityQuestion"),
            case.get("securityAnswer"),
            case.get("outcome"),
            case.get("lastUpdated")
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Inserted fraud case for {case.get('userName')}")
        return True
    except Exception as e:
        logger.error(f"Error inserting fraud case: {e}")
        return False