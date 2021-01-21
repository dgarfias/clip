# clip

usage: clip [-h] [-a ADDRESS] [-p PORT] [-b BYTES] [-o]

Simple script to synchronize clipboard between host and guest.

optional arguments:

  \-h, --help            show this help message and exit
  
  \-a ADDRESS, --address ADDRESS
                        IP address of the host (default: 127.0.0.1)

  \-p PORT, --port PORT  Port (default: 12000)
  
  \-b BYTES, --bytesize BYTES
                        Bytesize (default: 4096)

  \-o, --host            Run script as host (guest selected by default)

