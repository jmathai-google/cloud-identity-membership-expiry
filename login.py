#!/usr/bin/env python

import os
from oauth2client import file, client, tools

from cli import CLIENT_SECRET_OAUTH, SCOPES, TOKEN

def main():
    """ Build service object to make calls to the Cloud Identity API using its
        Discovery URL """
    if(not os.path.exists(CLIENT_SECRET_OAUTH)):
        exit("Please download your Oauth client file (client_secret_oauth.json).")

    # get the token if it exists
    # else start the oauth flow to get the token and save it
    store = file.Storage(TOKEN)
    flow = client.flow_from_clientsecrets(CLIENT_SECRET_OAUTH, SCOPES)
    credentials = tools.run_flow(flow, store)

if __name__ == "__main__":
    main()
