"""
Automatic file cleanup manager for uploaded and result files
Prevents storage accumulation on Render and other platforms
"""
import os
import time
import logging
import threading
import schedule
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)

class CleanupManager:
    """Manages automatic cleanup of temporary files"""
    
    def __init__(self, 
                 upload_folder: str = 'uploads',
                 result_folders: List[str] = None,
                 max_age_hours: int = 24,
                 max_total_size_mb: int = 100,
                 cleanup_interval_hours: int = 1):
        
        self.upload_folder = os.path.abspath(upload_folder)
        self.result_folders = [
            os.path.abspath(folder) for folder in 
            (result_folders or ['results', 'separate_results'])
        ]
        self.max_age_hours = max_age_hours
        self.max_total_size_mb = max_total_size_mb
        self.cleanup_interval_hours = cleanup_interval_hours
        self.running = False
        self.cleanup_thread = None
        
        # Ensure folders exist
        for folder in [self.upload_folder] + self.result_folders:
            os.makedirs(folder, exist_ok=True)
    
    def start_background_cleanup(self):
        """Start background cleanup scheduler"""
        if self.running:
            logger.warning("Cleanup manager already running")
            return
            
        self.running = True
        
        # Schedule cleanup tasks
        schedule.every(self.cleanup_interval_hours).hours.do(self._cleanup_old_files)
        schedule.every(30).minutes.do(self._cleanup_by_size)
        schedule.every(6).hours.do(self._cleanup_orphaned_sessions)
        
        # Start scheduler thread
        self.cleanup_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.cleanup_thread.start()
        
        logger.info(f"Started background cleanup - files older than {self.max_age_hours}h will be removed")
    
    def stop_background_cleanup(self):
        """Stop background cleanup"""
        self.running = False
        schedule.clear()
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
    
    def _run_scheduler(self):
        """Run the cleanup scheduler"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {e}")
    
    def _cleanup_old_files(self):
        """Remove files older than max_age_hours"""
        try:
            cutoff_time = time.time() - (self.max_age_hours * 3600)
            total_removed = 0
            total_size_freed = 0
            
            for folder in [self.upload_folder] + self.result_folders:
                if not os.path.exists(folder):
                    continue
                    
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            if os.path.getmtime(file_path) < cutoff_time:
                                file_size = os.path.getsize(file_path)
                                os.remove(file_path)
                                total_removed += 1
                                total_size_freed += file_size
                                logger.debug(f"Removed old file: {file_path}")
                        except (OSError, IOError) as e:
                            logger.warning(f"Could not remove {file_path}: {e}")
                    
                    # Remove empty directories
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            if not os.listdir(dir_path):  # Empty directory
                                os.rmdir(dir_path)
                                logger.debug(f"Removed empty directory: {dir_path}")
                        except (OSError, IOError):
                            pass  # Directory not empty or other error
            
            if total_removed > 0:
                size_mb = total_size_freed / (1024 * 1024)
                logger.info(f"Age cleanup: Removed {total_removed} files, freed {size_mb:.1f}MB")
                
        except Exception as e:
            logger.error(f"Error in age-based cleanup: {e}")
    
    def _cleanup_by_size(self):
        """Remove oldest files if total size exceeds limit"""
        try:
            max_size_bytes = self.max_total_size_mb * 1024 * 1024
            files_info = []
            
            # Collect all files with their info
            for folder in [self.upload_folder] + self.result_folders:
                if not os.path.exists(folder):
                    continue
                    
                for root, _, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stat = os.stat(file_path)
                            files_info.append({
                                'path': file_path,
                                'size': stat.st_size,
                                'mtime': stat.st_mtime
                            })
                        except (OSError, IOError):
                            continue
            
            # Calculate total size
            total_size = sum(f['size'] for f in files_info)
            
            if total_size <= max_size_bytes:
                return  # Under limit
            
            # Sort by modification time (oldest first)
            files_info.sort(key=lambda x: x['mtime'])
            
            # Remove oldest files until under limit
            removed_count = 0
            freed_size = 0
            
            for file_info in files_info:
                if total_size - freed_size <= max_size_bytes:
                    break
                
                try:
                    os.remove(file_info['path'])
                    removed_count += 1
                    freed_size += file_info['size']
                    logger.debug(f"Removed for size limit: {file_info['path']}")
                except (OSError, IOError) as e:
                    logger.warning(f"Could not remove {file_info['path']}: {e}")
            
            if removed_count > 0:
                freed_mb = freed_size / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                logger.info(f"Size cleanup: Removed {removed_count} files, freed {freed_mb:.1f}MB (was {total_mb:.1f}MB)")
                
        except Exception as e:
            logger.error(f"Error in size-based cleanup: {e}")
    
    def _cleanup_orphaned_sessions(self):
        """Remove files from sessions that no longer exist"""
        try:
            from security import secure_session_manager
            
            # Get all session files
            session_files = []
            session_pattern = r'session_\d{8}_\d{6}'
            
            for folder in [self.upload_folder] + self.result_folders:
                if not os.path.exists(folder):
                    continue
                    
                for root, _, files in os.walk(folder):
                    for file in files:
                        if 'session_' in file:
                            session_files.append(os.path.join(root, file))
            
            # Check which sessions are still active
            active_sessions = set()
            try:
                # Extract session IDs from filenames
                import re
                for file_path in session_files:
                    filename = os.path.basename(file_path)
                    match = re.search(session_pattern, filename)
                    if match:
                        session_id = match.group(0)
                        # Check if session is still active
                        if secure_session_manager.get_session(session_id):
                            active_sessions.add(session_id)
            except Exception as e:
                logger.warning(f"Could not check active sessions: {e}")
                return
            
            # Remove orphaned files
            removed_count = 0
            for file_path in session_files:
                try:
                    filename = os.path.basename(file_path)
                    match = re.search(session_pattern, filename)
                    if match:
                        session_id = match.group(0)
                        if session_id not in active_sessions:
                            os.remove(file_path)
                            removed_count += 1
                            logger.debug(f"Removed orphaned file: {file_path}")
                except Exception as e:
                    logger.warning(f"Could not remove orphaned file {file_path}: {e}")
            
            if removed_count > 0:
                logger.info(f"Orphan cleanup: Removed {removed_count} orphaned session files")
                
        except Exception as e:
            logger.error(f"Error in orphaned session cleanup: {e}")
    
    def manual_cleanup(self) -> Dict[str, int]:
        """Manually trigger all cleanup operations"""
        logger.info("Starting manual cleanup...")
        
        stats = {
            'files_before': 0,
            'files_after': 0,
            'size_before_mb': 0,
            'size_after_mb': 0
        }
        
        # Count before
        for folder in [self.upload_folder] + self.result_folders:
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stats['files_before'] += 1
                            stats['size_before_mb'] += os.path.getsize(file_path)
                        except (OSError, IOError):
                            pass
        
        stats['size_before_mb'] /= (1024 * 1024)
        
        # Run cleanup operations
        self._cleanup_old_files()
        self._cleanup_by_size()
        self._cleanup_orphaned_sessions()
        
        # Count after
        for folder in [self.upload_folder] + self.result_folders:
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            stats['files_after'] += 1
                            stats['size_after_mb'] += os.path.getsize(file_path)
                        except (OSError, IOError):
                            pass
        
        stats['size_after_mb'] /= (1024 * 1024)
        
        logger.info(f"Manual cleanup complete: {stats['files_before'] - stats['files_after']} files removed, "
                   f"{stats['size_before_mb'] - stats['size_after_mb']:.1f}MB freed")
        
        return stats
    
    def get_storage_stats(self) -> Dict[str, float]:
        """Get current storage statistics"""
        stats = {
            'total_files': 0,
            'total_size_mb': 0,
            'uploads_size_mb': 0,
            'results_size_mb': 0
        }
        
        # Uploads folder
        if os.path.exists(self.upload_folder):
            for root, _, files in os.walk(self.upload_folder):
                for file in files:
                    try:
                        file_size = os.path.getsize(os.path.join(root, file))
                        stats['total_files'] += 1
                        stats['total_size_mb'] += file_size
                        stats['uploads_size_mb'] += file_size
                    except (OSError, IOError):
                        pass
        
        # Result folders
        for folder in self.result_folders:
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for file in files:
                        try:
                            file_size = os.path.getsize(os.path.join(root, file))
                            stats['total_files'] += 1
                            stats['total_size_mb'] += file_size
                            stats['results_size_mb'] += file_size
                        except (OSError, IOError):
                            pass
        
        # Convert to MB
        stats['total_size_mb'] /= (1024 * 1024)
        stats['uploads_size_mb'] /= (1024 * 1024)
        stats['results_size_mb'] /= (1024 * 1024)
        
        return stats

# Global cleanup manager instance
cleanup_manager = CleanupManager(
    max_age_hours=24,  # Remove files older than 24 hours
    max_total_size_mb=100,  # Keep total storage under 100MB
    cleanup_interval_hours=1  # Check every hour
)