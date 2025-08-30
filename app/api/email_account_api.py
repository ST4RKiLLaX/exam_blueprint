from typing import List, Optional, Dict
from app.models.email_account import EmailAccount, email_account_manager
from app.models.agent import agent_manager


class EmailAccountAPI:
    """API layer for email account management operations"""
    
    @staticmethod
    def create_account(name: str, email_address: str, imap_host: str = "",
                      imap_port: int = 993, smtp_host: str = "", smtp_port: int = 587,
                      username: str = "", password: str = "", **kwargs) -> Dict:
        """Create a new email account and return result"""
        try:
            if not name.strip():
                return {"success": False, "error": "Account name is required"}
            
            if not email_address.strip():
                return {"success": False, "error": "Email address is required"}
            
            # Check for duplicate email addresses
            existing_accounts = email_account_manager.get_all_accounts()
            for account in existing_accounts:
                if account.email_address.lower() == email_address.lower().strip():
                    return {"success": False, "error": "Email address already exists"}
            
            account = email_account_manager.create_account(
                name=name.strip(),
                email_address=email_address.strip(),
                imap_host=imap_host.strip(),
                imap_port=imap_port,
                smtp_host=smtp_host.strip(),
                smtp_port=smtp_port,
                username=username.strip() or email_address.strip(),
                password=password,
                **kwargs
            )
            
            return {
                "success": True, 
                "account": account.to_dict(),
                "message": f"Email account '{name}' created successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_account(account_id: str) -> Dict:
        """Get email account by ID"""
        try:
            account = email_account_manager.get_account(account_id)
            if account:
                return {"success": True, "account": account.to_dict()}
            else:
                return {"success": False, "error": "Email account not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_all_accounts() -> Dict:
        """Get all email accounts"""
        try:
            accounts = email_account_manager.get_all_accounts()
            return {
                "success": True, 
                "accounts": [account.to_dict() for account in accounts],
                "count": len(accounts)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_active_accounts() -> Dict:
        """Get all active email accounts"""
        try:
            accounts = email_account_manager.get_active_accounts()
            return {
                "success": True, 
                "accounts": [account.to_dict() for account in accounts],
                "count": len(accounts)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    

    @staticmethod
    def update_account(account_id: str, **kwargs) -> Dict:
        """Update an email account"""
        try:
            # Remove empty values and clean up data
            update_data = {k: v for k, v in kwargs.items() if v is not None}
            if "name" in update_data and not update_data["name"].strip():
                return {"success": False, "error": "Account name cannot be empty"}
            
            if "email_address" in update_data:
                email_address = update_data["email_address"].strip()
                if not email_address:
                    return {"success": False, "error": "Email address cannot be empty"}
                
                # Check for duplicate email addresses (excluding current account)
                existing_accounts = email_account_manager.get_all_accounts()
                for account in existing_accounts:
                    if (account.account_id != account_id and 
                        account.email_address.lower() == email_address.lower()):
                        return {"success": False, "error": "Email address already exists"}
                
                update_data["email_address"] = email_address
            
            success = email_account_manager.update_account(account_id, **update_data)
            if success:
                account = email_account_manager.get_account(account_id)
                return {
                    "success": True, 
                    "account": account.to_dict(),
                    "message": "Email account updated successfully"
                }
            else:
                return {"success": False, "error": "Email account not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def delete_account(account_id: str) -> Dict:
        """Delete an email account"""
        try:
            account = email_account_manager.get_account(account_id)
            if not account:
                return {"success": False, "error": "Email account not found"}
            
            # Remove account from all agents first
            agents = agent_manager.get_all_agents()
            for agent in agents:
                if account_id in agent.email_accounts:
                    agent.email_accounts.remove(account_id)
                    agent_manager.update_agent(agent.agent_id, email_accounts=agent.email_accounts)
            
            success = email_account_manager.delete_account(account_id)
            if success:
                return {
                    "success": True, 
                    "message": f"Email account '{account.name}' deleted successfully"
                }
            else:
                return {"success": False, "error": "Failed to delete email account"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    

    @staticmethod
    def test_connection(account_id: str) -> Dict:
        """Test email account connection"""
        try:
            return email_account_manager.test_connection(account_id)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_accounts_with_agent_info() -> Dict:
        """Get all accounts with basic information"""
        try:
            accounts = email_account_manager.get_all_accounts()
            
            accounts_with_info = []
            for account in accounts:
                account_dict = account.to_dict()
                accounts_with_info.append(account_dict)
            
            return {
                "success": True,
                "accounts": accounts_with_info,
                "count": len(accounts_with_info)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
