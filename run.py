"""Run the webhook-ec2 trading server.

Thin entry-point: import the server module and start listening.
"""

from webhook.server import main

if __name__ == "__main__":
    main()
