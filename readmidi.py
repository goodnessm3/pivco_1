from machine import UART, Pin
import time

# control numbers from the Arturia keyboard, hardcoded
FADERS = [73, 75, 79, 72, 80, 81, 82, 83, 85]
KNOBS = [74, 71, 76, 77, 93, 18, 19, 16, 17]

# !!! USE 1 not 0!!!!
uart0 = UART(1, baudrate=31250, rx=Pin(5))
# !!! EXTREMELY HECKIN IMPORTANT
# UART(1... with tx, rx = 1,2 will CLASH with PIOs used for FREQ MEASUREMENT
# problem manifests as PIOs just not filling their buffers
# HARD TO DIAGNOSE AND WASTED AN ENTIRE WEEKEND

def format_bytes_nibbles(data: bytearray) -> str:
    lines = []
    for b in data:
        # Format to 8-bit binary
        bits = f"{b:08b}"
        # Split into nibbles
        lines.append(bits[:4] + " " + bits[4:])
    return " ".join(lines)


   
class MidiReader:
    
    def __init__(self):
    
        self.queue = []
        self.rxData = bytearray()
        self.channel = None  # always 0 for now
        self.awaiting_note_index = False
        self.awaiting_velocity = False
        
        self.awaiting_control_channel = False
        self.awaiting_control_value = False
        
        self.note_queue = []  # accumulate a note on message here
        self.control_queue = []  # for controller messages
      
    def read(self):
        
        """Accumulate messages from the UART buffer into our own
        internal message queue"""

        l = uart0.any()
        if l > 0:
            dat = uart0.read(l)
            if dat:
                self.rxData.extend(dat)
                
        
        for b in self.rxData:  # iterate thru all the MIDI messages

            if b & 0xF0 == 144:  # note on. 0xF0 masks out the right 4 bits
                #print("notedn")
                # 144 = 0x90 = note down
                channel = b & 15  # always channel 0 from my keyboard as default
                self.note_queue.append(True)  # we collected a note down signal
                # expect the frequency to come next, then the velocity
                self.awaiting_note_index = True
                continue
            
            if b & 0xF0 == 128:  # 128 = note off (0x80)
                #print("noteup")
                channel = b & 15  # always channel 0 from my keyboard as default
                self.note_queue.append(False)
                self.awaiting_note_index = True
                continue
            
            if b & 0xF0 == 176:
                # control message from faders and rotary encoders
                # for the Arturia keyboard it's always channel 0
                self.awaiting_control_channel = True
                continue
            
            if self.awaiting_note_index:  # accumulating info about note down/up
                #print("noteinedx")
                self.note_queue.append(b)
                self.awaiting_note_index = False
                self.awaiting_velocity = True
                continue
            
            elif self.awaiting_velocity:
                #print("notevelocity")
                velocity = b  # not using this for now
                self.awaiting_velocity = False
                continue
   
            if self.awaiting_control_channel:
                self.control_queue.append(b)  # add the control channel byte
                self.awaiting_control_channel = False
                self.awaiting_control_value = True
                continue
            
            if self.awaiting_control_value:
                self.control_queue.append(b * 2)
                # !!NOTE manually multiplying by 2. Keyboard controls give 0-127 but everything else works on
                # 8-bit so we just convert it as soon as it comes in to the system
                self.awaiting_control_value = False
                continue
            
        self.rxData = bytearray()

    
    def get_messages(self, queue_type):
        
        if queue_type == "notes":
            q = self.note_queue
        elif queue_type == "controls":
            q = self.control_queue
        else:
            raise KeyError("unrecognized message type")
        
        qlen = len(q)
        out = []
        
        # for now, queues only have pairs of messages
        # (Note on True/False, note value)
        # (Controller number, controller value)
        if qlen % 2 == 0 and qlen > 0:
            idx = 0
            while idx < qlen:
                out.append((q[idx], q[idx+1]))
                idx += 2  # go through the queue and accumulate pairs of values
            q.clear()
                
        return out
        
"""    
import time
MR = MidiReader()
while 1:
    time.sleep(0.5)
    print("result:", list(MR.read()))
"""