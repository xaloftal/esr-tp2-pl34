# colors.py
# ANSI color codes for terminal output

class Colors:
    """ANSI color codes for terminal output"""
    # Regular colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright/Bold colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    
    # Styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    BLINK = '\033[5m'
    REVERSE = '\033[7m'
    
    # Reset
    RESET = '\033[0m'
    
    @staticmethod
    def color(text, color_code):
        """Wrap text with color code"""
        return f"{color_code}{text}{Colors.RESET}"

# Convenience functions for common message types
def topology_log(text):
    """Color for TOPOLOGY messages (bootstrapper, neighbors, initialization)"""
    return Colors.color(text, Colors.CYAN)

def flood_log(text):
    """Color for FLOOD protocol messages"""
    return Colors.color(text, Colors.BRIGHT_CYAN)

def stream_log(text):
    """Color for STREAM messages"""
    return Colors.color(text, Colors.BRIGHT_GREEN)

def rtp_log(text):
    """Color for RTP messages"""
    return Colors.color(text, Colors.BRIGHT_BLUE)

def error_log(text):
    """Color for ERROR messages"""
    return Colors.color(text, Colors.BRIGHT_RED)

def warning_log(text):
    """Color for WARNING messages"""
    return Colors.color(text, Colors.BRIGHT_YELLOW)

def route_log(text):
    """Color for ROUTE messages"""
    return Colors.color(text, Colors.BRIGHT_MAGENTA)

def heartbeat_log(text):
    """Color for HEARTBEAT messages"""
    return Colors.color(text, Colors.DIM + Colors.WHITE)

def video_log(video_name):
    """Get consistent color for a specific video stream"""
    # More colors for better distribution
    video_colors = [
        Colors.BRIGHT_GREEN,
        Colors.BRIGHT_YELLOW,
        Colors.BRIGHT_BLUE,
        Colors.BRIGHT_MAGENTA,
        Colors.BRIGHT_CYAN,
        Colors.GREEN,
        Colors.YELLOW,
        Colors.BLUE,
        Colors.MAGENTA,
    ]
    # Use a polynomial rolling hash for better distribution
    hash_val = 0
    prime = 53  # Prime number for better distribution
    for i, c in enumerate(video_name):
        hash_val = (hash_val * prime + ord(c)) 
    return video_colors[abs(hash_val) % len(video_colors)]

def rtp_forward_log(video_name, text):
    """Color for RTP forwarding based on video"""
    color = video_log(video_name)
    return Colors.color(text, color)
