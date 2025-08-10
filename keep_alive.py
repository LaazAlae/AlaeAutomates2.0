"""
Keep-alive system to prevent Render free tier from sleeping
Pings the app every 14 minutes to maintain activity
"""
import threading
import time
import requests
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class KeepAliveManager:
    """Manages keep-alive pings to prevent app from sleeping on Render"""
    
    def __init__(self, app_url: str = None, ping_interval: int = 840):  # 14 minutes
        self.app_url = app_url or self._get_app_url()
        self.ping_interval = ping_interval
        self.running = False
        self.ping_thread = None
        self.total_pings = 0
        self.failed_pings = 0
        self.last_ping_time = None
        self.last_ping_status = None
        
    def _get_app_url(self) -> str:
        """Get app URL from environment or construct default"""
        # Try to get from Render environment variables
        render_external_url = os.environ.get('RENDER_EXTERNAL_URL')
        if render_external_url:
            return render_external_url
            
        # Try to construct from other env vars
        app_name = os.environ.get('RENDER_SERVICE_NAME', 'alaeautomates')
        return f"https://{app_name}.render.com"
    
    def start_keep_alive(self):
        """Start the keep-alive ping system"""
        if self.running:
            logger.warning("Keep-alive already running")
            return
            
        # Only start if we're likely on Render (production)
        if not self._should_run_keep_alive():
            logger.info("Keep-alive disabled - not in production environment")
            return
            
        self.running = True
        self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self.ping_thread.start()
        logger.info(f"Started keep-alive pings to {self.app_url} every {self.ping_interval/60:.1f} minutes")
    
    def stop_keep_alive(self):
        """Stop the keep-alive system"""
        self.running = False
        if self.ping_thread:
            self.ping_thread.join(timeout=5)
        logger.info("Stopped keep-alive system")
    
    def _should_run_keep_alive(self) -> bool:
        """Determine if keep-alive should run based on environment"""
        # Run if in production or explicitly enabled
        if os.environ.get('FLASK_ENV') == 'production':
            return True
        if os.environ.get('ENABLE_KEEP_ALIVE', '').lower() == 'true':
            return True
        if 'render.com' in self.app_url:
            return True
        return False
    
    def _ping_loop(self):
        """Main ping loop"""
        # Initial delay to let app fully start
        time.sleep(60)
        
        while self.running:
            try:
                self._perform_ping()
                time.sleep(self.ping_interval)
            except Exception as e:
                logger.error(f"Error in keep-alive loop: {e}")
                time.sleep(300)  # Wait 5 minutes before retrying
    
    def _perform_ping(self):
        """Perform a single ping to the app"""
        try:
            ping_url = f"{self.app_url}/health"
            
            # Perform the ping with timeout
            response = requests.get(
                ping_url, 
                timeout=30,
                headers={
                    'User-Agent': 'AlaeAutomates-KeepAlive/1.0',
                    'X-Keep-Alive': 'true'
                }
            )
            
            self.total_pings += 1
            self.last_ping_time = datetime.now()
            
            if response.status_code == 200:
                self.last_ping_status = 'success'
                logger.info(f"Keep-alive ping successful #{self.total_pings} (status: {response.status_code})")
            else:
                self.failed_pings += 1
                self.last_ping_status = f'failed_{response.status_code}'
                logger.warning(f"Keep-alive ping failed #{self.total_pings}: {response.status_code}")
                
        except requests.exceptions.Timeout:
            self.failed_pings += 1
            self.last_ping_status = 'timeout'
            logger.warning(f"Keep-alive ping timeout #{self.total_pings}")
            
        except requests.exceptions.ConnectionError:
            self.failed_pings += 1
            self.last_ping_status = 'connection_error'
            logger.warning(f"Keep-alive ping connection error #{self.total_pings}")
            
        except Exception as e:
            self.failed_pings += 1
            self.last_ping_status = f'error_{type(e).__name__}'
            logger.error(f"Keep-alive ping error #{self.total_pings}: {e}")
    
    def get_stats(self) -> dict:
        """Get keep-alive statistics"""
        return {
            'running': self.running,
            'app_url': self.app_url,
            'total_pings': self.total_pings,
            'failed_pings': self.failed_pings,
            'success_rate': round((self.total_pings - self.failed_pings) / max(1, self.total_pings) * 100, 2),
            'last_ping_time': self.last_ping_time.isoformat() if self.last_ping_time else None,
            'last_ping_status': self.last_ping_status,
            'ping_interval_minutes': round(self.ping_interval / 60, 1)
        }
    
    def manual_ping(self) -> dict:
        """Manually trigger a ping for testing"""
        try:
            self._perform_ping()
            return {
                'status': 'success',
                'message': f'Manual ping completed. Status: {self.last_ping_status}',
                'stats': self.get_stats()
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Manual ping failed: {str(e)}',
                'stats': self.get_stats()
            }

# Global keep-alive manager instance
keep_alive_manager = KeepAliveManager()

# Alternative external ping services (backup solutions)
EXTERNAL_PING_SERVICES = [
    {
        'name': 'UptimeRobot',
        'description': 'Free monitoring service that pings every 5 minutes',
        'url': 'https://uptimerobot.com/',
        'setup': 'Create monitor with your Render URL'
    },
    {
        'name': 'Pingdom',
        'description': 'Website monitoring with free tier',
        'url': 'https://www.pingdom.com/',
        'setup': 'Add uptime check for your Render domain'
    },
    {
        'name': 'StatusCake',
        'description': 'Free website monitoring',
        'url': 'https://www.statuscake.com/',
        'setup': 'Create uptime test for your app'
    },
    {
        'name': 'Freshping',
        'description': 'Free uptime monitoring',
        'url': 'https://freshping.io/',
        'setup': 'Add check for your Render URL'
    }
]

def get_external_ping_services():
    """Get list of recommended external ping services"""
    return EXTERNAL_PING_SERVICES