#!/usr/bin/env python3

import argparse
import json
import os
import re

from dateutil.parser import parse
from tabulate import tabulate

""" groups service client """
from googleapiclient.discovery import build
from google.oauth2 import service_account
from apiclient.discovery import build
from httplib2 import Http
from urllib.parse import urlencode
from oauth2client import file, client, tools


# Cloud identity groups api scope
SCOPES = ["https://www.googleapis.com/auth/cloud-identity.groups"]
SERVICE_ACCOUNT_FILE = "{}/client_secrets_service_account.json".format(
                            os.path.dirname(os.path.realpath(__file__))
                        )
API_KEY_FILE = "{}/api_key.txt".format(
                            os.path.dirname(os.path.realpath(__file__))
                        )

def build_service(credential_path, client_secret_path):
    """ Build service object to make calls to the Cloud Identity API using its
        Discovery URL """
    if(not os.path.exists(API_KEY_FILE)):
        exit("Please create a file with your API key at {}".format(API_KEY_FILE))

    # store the API key
    with open(API_KEY_FILE) as key_file:
        api_key = key_file.read()

    # get the token if it exists
    # else start the oauth flow to get the token and save it
    store = file.Storage('token.json')
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets('client_secret_oauth.json', SCOPES)
        credentials = tools.run_flow(flow, store)

    service_name = "cloudidentity.googleapis.com"
    api_name = "cloudidentity"
    api_version = "v1alpha1"
    # NOTE: since this API is in alpha we need to pass
    #   the GOOGLE_GROUPS_API_TRUSTED_TESTERS label
    #   to have v1alpha1 included in the discovery document
    # we also need to pass in an API key else the label parameter
    #   doesn't give us v1alpha1 included in the response
    discovery_url = (
        "https://{}/$discovery/rest?version={}&key={}&labels=GOOGLE_GROUPS_API_TRUSTED_TESTERS".format(
            service_name, api_version, api_key
        )
    )
    service = build(
                  api_name,
                  api_version,
                  discoveryServiceUrl=discovery_url,
                  credentials=credentials,
                  developerKey=api_key,
              )
    return service


def groups_create(service, customer_id, key, display_name='', description=''):
    """Create a group.
    Args:
        service: service client.
        customer_id: your customer ID
        key: the group's key in email address format
        description: a description for the group
        display_name: a display name for the group
    Returns: the created group
    """
    group = {
        "parent": "customerId/{}".format(customer_id),
        "groupKey": {"id": key},
        "description": str(description),
        "displayName": str(display_name),
        # the discussion_forum label is the only label currently supported
        "labels": {"system/groups/discussion_forum": ""}
    }

    try:
        request = service.groups().create(body=group)
        request.uri += "&initialGroupConfig=WITH_INITIAL_OWNER"
        response = request.execute()
        group = groups_get(service, name=response['response']['name'])
        return group
    except Exception as e:
        return e

def groups_get(service, name=None, key=None):
    """Get a group by either name or key.

    Args:
        service: service client.
        name: the name of the group (i.e. groups/abcdefghijklmmnop
        key: id of the group in email format
    Returns: Group resource if found.
    """
    try:
        # if id is passed we then we have to fetch the name
        if(id is not None):
            param = "&groupKey.id=" + key
            lookup_group_name_request = service.groups().lookup()
            lookup_group_name_request.uri += param
            lookup_group_name_response = lookup_group_name_request.execute()
            name = lookup_group_name_response.get("name")

        response = [service.groups().get(name=name).execute()]
        return response
    except Exception as e:
        return e

def groups_list(service, customer_id, page_size, view):
    """List groups.

    Args:
        service: service client.
        customer_id: your customer ID
        page_size: page size for pagination.
        view: FULL / BASIC view of groups.
    Returns: List of groups.
    """
    search_query = urlencode({
            # this gets all groups in the customer the caller has permission to view with the discussion_forum label
            "query": "parent=='customerId/{}' && 'system/groups/discussion_forum' in labels".format(customer_id),
            "pageSize": page_size,
            "view": view
        }
    )
    try:
        search_groups_request = service.groups().search()
        search_groups_request.uri += "&" + search_query
        groups = search_groups_request.execute()['groups']
        return groups
    except Exception as e:
        return e

def memberships_list(service, name=None):
    """List memberships of a group.

    Args:
        service: service client.
        name: name of the group (i.e. groups/abcdefghijklmnop)
    Returns: List of groups.
    """
    try:
        members_request = service.groups().memberships().list(parent=name)
        members_request.uri += "&view=FULL"
        members_response = members_request.execute()['memberships']
        # Only memberships with an expire time will return that field
        #   so we insert it for display purposes if it's not there
        if('expireTime' not in members_response[0].keys()):
            members_response[0]['expireTime'] = ''
        return members_response
    except Exception as e:
        return e

def memberships_get(service, name=None):
    """Get a membership.

    Args:
        service: service client.
        name: name of the membership (i.e. groups/abcdefghijklmnop/memberships/1234567890)
    Returns: Membership resource.
    """
    try:
        response = service.groups().memberships().get(
                name=name).execute()
        return [response]
    except Exception as e:
        return e

def memberships_create(service, name=None, member=None, expiry=None):
    """Create group membership.

    Args:
        service: service client.
        name: name of the group the membership is being created in (i.e. groups/abcdefghijklmnop)
        member: email address of the member being created (i.e. user@domain.com or group@domain.com)
        expiry: unix timestamp or parsable time string (i.e. Nov 30 2019)
    Returns: Membership resource.
    """
    # Build lookup group query
    try:
        membership = {"name":"", "preferred_member_key": {"id": member}, "roles": [{"name": "MEMBER"}]}
        if(expiry):
            membership["expiry_detail"] = {
                "expire_time": {
                    "seconds": get_expiry(expiry)
                 }
            }
        response = service.groups().memberships().create(
                parent=name, body=membership).execute()
        member = memberships_get(service, name=response['response']['name'])
        return member
    except Exception as e:
        return e

def get_expiry(expiry):
    """Convenience function to be able to parse a string into a timestamp"""
    if(re.search("^[0-9]+$", expiry)):
        return expiry
    else:
        return parse(expiry).strftime("%s")

def membership_expire(service, name=None, member=None, expiry=None):
    """Set an expiration on a membership.

    Args:
        service: service client.
        name: name of the group the membership is being created in (i.e. groups/abcdefghijklmnop)
        member: email address of the member being created (i.e. user@domain.com or group@domain.com)
        expiry: unix timestamp or parsable time string (i.e. Nov 30 2019)
    Returns: Membership resource.
    """
    # Build lookup group query
    try:
        membership = {"expiry_detail": {
            "expire_time": {
                "seconds": get_expiry(expiry)
             }
        }}
        request = service.groups().memberships().patch(
                name=name, body=membership)
        request.uri += "&updateMask=expiryDetail.expireTime"
        response = request.execute()
        return response
    except Exception as e:
        return e

def render(*args):
    """Takes a list of dictionaries and prints them out in a table"""
    for arg in args:
        if(isinstance(arg, Exception)):
            render_exception(arg)
        else:
            output = []
            output.append(list(arg[0].keys()))
            """if('expireTime' not in output[0]):
                output[0].append('expireTime')"""

            for row in arg:
                output.append(list(row.values()))
            print(tabulate(output, headers="firstrow"))

def render_exception(e):
    """Special handling to display exceptions consistently"""
    print(e)
    if(hasattr(e, 'content')):
        print(json.dumps(json.loads(e.content), indent=4, sort_keys=True))


def main():
    """Main program"""
    # set up parsing of command line params
    parser = argparse.ArgumentParser(description='Command line tool to use the Cloud Identity Groups API.')
    parser.add_argument('command', type=str, metavar='C', nargs=1, help='Command to execute, one of (groups.create, groups.list, groups.get, memberships.create, memberships.list, memberships.expire)', choices=['groups.list','groups.get', 'groups.create', 'memberships.list', 'memberships.create', 'memberships.expire'])
    parser.add_argument('--customer', help='Your customer id')
    parser.add_argument('--name', help='Group name for get or update')
    parser.add_argument('--displayName', help='Display name when creating a group')
    parser.add_argument('--description', help='Description name when creating a group')
    parser.add_argument('--member', help='Member (email address)')
    parser.add_argument('--expiry', help='Member expiration')
    parser.add_argument('--key', help='Group key (email address) for get or update')
    parser.add_argument('--count', help='Number of groups to return')
    args = parser.parse_args()

    # build the service which will be passed in to all functions to make an API call
    service = build_service('oauth_tokens.json', 'client_secrets.json')

    # handle each of the commands
    if(args.command[0] == 'groups.list'):
        if(args.customer):
            count = 10
            if(args.count):
                count = args.count
            groups = groups_list(service, args.customer, count, "BASIC")
            render(groups)
            return
        else:
            print("Please pass your customer id `--customer C03n72mjq`")
    elif(args.command[0] == 'groups.get'):
        if(args.name):
            group = groups_get(service, name=args.name)
            render(group)
            return
        elif(args.key):
            group = groups_get(service, key=args.key)
            render(group)
            return
        else:
            print("Please pass the group name `--name groups/041mghml1gu72pq` or `--id groupkey@domain.com`")
            return
    elif(args.command[0] == 'groups.create'):
        if(args.customer and args.key):
            group = groups_create(service, args.customer, args.key, display_name=args.displayName, description=args.description)
            render(group)
            return
        else:
            print("Please pass a customer `--customer C03n72mjq` and group key `--key groupkey@domain.com`")
            return
    elif(args.command[0] == 'memberships.list'):
        if(args.name):
            members = memberships_list(service, name=args.name)
            render(members)
            return
        else:
            print("Please pass the group name `--name groups/041mghml1gu72pq` or `--id groupkey@domain.com`")
            return
    elif(args.command[0] == 'memberships.expire'):
        if(args.name and args.member):
            members = membership_expire(service, name=args.name, member=args.member, expiry=args.expiry)
            render(members)
            return
        else:
            print("Please pass the group name `--name groups/041mghml1gu72pq` or `--id groupkey@domain.com` and the member to be added `--member user@domain.com`")
            return
    elif(args.command[0] == 'memberships.create'):
        if(args.name):
            members = memberships_create(service, name=args.name, member=args.member, expiry=args.expiry)
            render(members)
            return
        else:
            print("Please pass the group name `--name groups/041mghml1gu72pq` or `--id groupkey@domain.com`")
            return
    return

if __name__ == "__main__":
    main()
