from django.contrib.auth import authenticate,login,logout

class AuthenticationService:
    """
    Handles all authentication related business logic.
    """
    
    @staticmethod
    def login_user(request,username:str, password:str):
        """
        Authenticate user and create session.
        """
        user = authenticate(request=request,username=username,password=password)
        
        if user is None:
            return None
        
        login(request,user) # This is where the session is actually created.->generate a session id, store it in the session backend, send a cookie->Browser receives session id
        return user #If successful, the view gets <User: Greeshma>