# video_mapping.py
# Handles video name to SSRC mapping for RTP packets

import threading

def video_name_to_ssrc(video_name):
    """
    Convert video name to a unique SSRC (32-bit integer).
    Uses a simple hash function to ensure consistent mapping.
    """
    if not video_name:
        return 0
    
    # Simple hash: sum of character codes multiplied by position
    # and constrained to 32-bit unsigned integer
    hash_value = 0
    for i, char in enumerate(video_name):
        hash_value = (hash_value * 31 + ord(char)) & 0xFFFFFFFF
    
    return hash_value

def ssrc_to_video_name(ssrc, video_map=None):
    """
    Convert SSRC back to video name using a mapping dictionary.
    If no mapping provided, returns a generic identifier.
    
    Args:
        ssrc: The SSRC value from RTP packet
        video_map: Optional dict mapping {ssrc: video_name}
    
    Returns:
        Video name string or None
    """
    if video_map and ssrc in video_map:
        return video_map[ssrc]
    
    # If no mapping, return None (caller should handle)
    return None

class VideoMapper:
    """
    Maintains bidirectional mapping between video names and SSRC values.
    Thread-safe for concurrent access.
    """
    def __init__(self):
        self.name_to_ssrc = {}  # {video_name: ssrc}
        self.ssrc_to_name = {}  # {ssrc: video_name}
        self.lock = threading.Lock()  # Protect dictionary access
    
    def register_video(self, video_name):
        """Register a video and return its SSRC. Thread-safe."""
        with self.lock:
            if video_name in self.name_to_ssrc:
                return self.name_to_ssrc[video_name]
            
            ssrc = video_name_to_ssrc(video_name)
            self.name_to_ssrc[video_name] = ssrc
            self.ssrc_to_name[ssrc] = video_name
            return ssrc
    
    def get_ssrc(self, video_name):
        """Get SSRC for a video name. Thread-safe."""
        with self.lock:
            return self.name_to_ssrc.get(video_name, video_name_to_ssrc(video_name))
    
    def get_video_name(self, ssrc):
        """Get video name for an SSRC. Thread-safe."""
        with self.lock:
            return self.ssrc_to_name.get(ssrc, None)
    
    def get_mapping(self):
        """Get the SSRC to video name mapping dict. Thread-safe."""
        with self.lock:
            return self.ssrc_to_name.copy()
