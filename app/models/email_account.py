import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from cryptography.fernet import Fernet
import base64

class EmailAccount:
    """Represents an email account configuration"""
    
    def __init__(self, account_id: str = None, name: str = "", email_address: str = "",
                 imap_host: str = "", imap_port: int = 993, imap_ssl: bool = True,
                 smtp_host: str = "", smtp_port: int = 587, smtp_ssl: bool = True,
                 username: str = "", password: str = "", status: str = "active",
                 created_at: str = None, updated_at: str = None):
        self.account_id = account_id or str(uuid.uuid4())
        self.name = name
        self.email_address = email_address
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_ssl = imap_ssl
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_ssl = smtp_ssl
        self.username = username or email_address
        self.password = password  # Will be encrypted when stored
        self.status = status  # active, inactive, error
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
    
    def to_dict(self, include_password: bool = False) -> Dict:
        """Convert email account to dictionary for JSON serialization"""
        data = {
            "account_id": self.account_id,
            "name": self.name,
            "email_address": self.email_address,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "imap_ssl": self.imap_ssl,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_ssl": self.smtp_ssl,
            "username": self.username,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        
        if include_password:
            data["password"] = self.password
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'EmailAccount':
        """Create email account from dictionary"""
        # Filter out legacy fields that are no longer supported
        filtered_data = {k: v for k, v in data.items() if k != 'assigned_agents'}
        return cls(**filtered_data)
    
    def update(self, **kwargs):
        """Update email account properties and set updated_at timestamp"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()


class EmailAccountManager:
    """Manages email accounts with encryption for passwords"""
    
    def __init__(self, storage_path: str = None, encryption_key: str = None):
        self.storage_path = storage_path or os.path.join(
            os.path.dirname(__file__), "..", "config", "email_accounts.json"
        )
        self.encryption_key_path = os.path.join(
            os.path.dirname(self.storage_path), "email_encryption.key"
        )
        self._accounts = {}
        self._setup_encryption()
        self.load_accounts()
    
    def _setup_encryption(self):
        """Setup encryption for password storage"""
        if os.path.exists(self.encryption_key_path):
            with open(self.encryption_key_path, 'rb') as f:
                self.encryption_key = f.read()
        else:
            # Generate new encryption key
            self.encryption_key = Fernet.generate_key()
            os.makedirs(os.path.dirname(self.encryption_key_path), exist_ok=True)
            with open(self.encryption_key_path, 'wb') as f:
                f.write(self.encryption_key)
        
        self.cipher_suite = Fernet(self.encryption_key)
    
    def _encrypt_password(self, password: str) -> str:
        """Encrypt password for storage"""
        if not password:
            return ""
        encrypted = self.cipher_suite.encrypt(password.encode())
        return base64.b64encode(encrypted).decode()
    
    def _decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt password from storage"""
        if not encrypted_password:
            return ""
        try:
            encrypted_bytes = base64.b64decode(encrypted_password.encode())
            decrypted = self.cipher_suite.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception:
            return ""
    
    def load_accounts(self):
        """Load email accounts from storage"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for account_id, account_data in data.get("accounts", {}).items():
                        # Decrypt password when loading
                        if account_data.get("password"):
                            account_data["password"] = self._decrypt_password(account_data["password"])
                        self._accounts[account_id] = EmailAccount.from_dict(account_data)
            except (json.JSONDecodeError, FileNotFoundError):
                self._accounts = {}
    
    def save_accounts(self):
        """Save email accounts to storage with encrypted passwords"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        # Prepare data for storage with encrypted passwords
        storage_data = {}
        for account_id, account in self._accounts.items():
            account_dict = account.to_dict(include_password=True)
            if account_dict.get("password"):
                account_dict["password"] = self._encrypt_password(account_dict["password"])
            storage_data[account_id] = account_dict
        
        data = {"accounts": storage_data}
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def create_account(self, name: str, email_address: str, imap_host: str = "",
                      imap_port: int = 993, smtp_host: str = "", smtp_port: int = 587,
                      username: str = "", password: str = "", **kwargs) -> EmailAccount:
        """Create a new email account"""
        account = EmailAccount(
            name=name,
            email_address=email_address,
            imap_host=imap_host,
            imap_port=imap_port,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            username=username or email_address,
            password=password,
            **kwargs
        )
        self._accounts[account.account_id] = account
        self.save_accounts()
        return account
    
    def get_account(self, account_id: str) -> Optional[EmailAccount]:
        """Get email account by ID"""
        return self._accounts.get(account_id)
    
    def get_all_accounts(self) -> List[EmailAccount]:
        """Get all email accounts"""
        return list(self._accounts.values())
    
    def get_active_accounts(self) -> List[EmailAccount]:
        """Get all active email accounts"""
        return [account for account in self._accounts.values() if account.status == "active"]
    
    def update_account(self, account_id: str, **kwargs) -> bool:
        """Update an email account"""
        account = self._accounts.get(account_id)
        if account:
            account.update(**kwargs)
            self.save_accounts()
            return True
        return False
    
    def delete_account(self, account_id: str) -> bool:
        """Delete an email account"""
        if account_id in self._accounts:
            del self._accounts[account_id]
            self.save_accounts()
            return True
        return False
    
    def test_connection(self, account_id: str) -> Dict:
        """Test email account connection with detailed error reporting"""
        account = self._accounts.get(account_id)
        if not account:
            return {"success": False, "error": "Account not found"}
        
        results = {
            "imap_test": {"success": False, "error": ""},
            "smtp_test": {"success": False, "error": ""}
        }
        
        # Test IMAP connection
        try:
            import imaplib
            import ssl
            
            print(f"Testing IMAP connection to {account.imap_host}:{account.imap_port}")
            print(f"Username: {account.username}")
            print(f"SSL: {account.imap_ssl}")
            
            if account.imap_ssl:
                imap = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
            else:
                imap = imaplib.IMAP4(account.imap_host, account.imap_port)
            
            imap.login(account.username, account.password)
            imap.select('INBOX')
            imap.logout()
            
            results["imap_test"]["success"] = True
            results["imap_test"]["message"] = "IMAP connection successful"
            
        except imaplib.IMAP4.error as e:
            results["imap_test"]["error"] = f"IMAP authentication failed: {str(e)}"
        except Exception as e:
            results["imap_test"]["error"] = f"IMAP connection error: {str(e)}"
        
        # Test SMTP connection
        try:
            import smtplib
            
            print(f"Testing SMTP connection to {account.smtp_host}:{account.smtp_port}")
            print(f"SSL: {account.smtp_ssl}")
            
            if account.smtp_ssl or account.smtp_port == 465:
                # Use SMTP_SSL for port 465 or when SSL is explicitly enabled
                smtp = smtplib.SMTP_SSL(account.smtp_host, account.smtp_port)
            else:
                # Use regular SMTP with STARTTLS for ports like 587
                smtp = smtplib.SMTP(account.smtp_host, account.smtp_port)
                if account.smtp_port not in [25, 465]:  # Don't use STARTTLS on ports 25 or 465
                    smtp.starttls()
            
            smtp.login(account.username, account.password)
            smtp.quit()
            
            results["smtp_test"]["success"] = True
            results["smtp_test"]["message"] = "SMTP connection successful"
            
        except smtplib.SMTPAuthenticationError as e:
            results["smtp_test"]["error"] = f"SMTP authentication failed: {str(e)}"
        except Exception as e:
            results["smtp_test"]["error"] = f"SMTP connection error: {str(e)}"
        
        # Determine overall success
        overall_success = results["imap_test"]["success"] and results["smtp_test"]["success"]
        
        if overall_success:
            self.update_account(account_id, status="active")
            return {
                "success": True, 
                "message": "Both IMAP and SMTP connections successful",
                "details": results
            }
        else:
            self.update_account(account_id, status="error")
            error_messages = []
            if not results["imap_test"]["success"]:
                error_messages.append(f"IMAP: {results['imap_test']['error']}")
            if not results["smtp_test"]["success"]:
                error_messages.append(f"SMTP: {results['smtp_test']['error']}")
            
            return {
                "success": False, 
                "error": " | ".join(error_messages),
                "details": results
            }


# Global email account manager instance
email_account_manager = EmailAccountManager()
