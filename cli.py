#!/usr/bin/env python

import argparse
import json
import os
import re

import click
from dateutil.parser import parse
from tabulate import tabulate

""" groups service client """
from googleapiclient.discovery import build
from httplib2 import Http
from six.moves.urllib.parse import urlencode
from oauth2client import file, client, tools
from google.oauth2 import service_account


# Cloud identity groups api scope
SCOPES = ["https://www.googleapis.com/auth/cloud-identity.groups"]
API_KEY_FILE = "{}/api_key.txt".format(
                            os.path.dirname(os.path.realpath(__file__))
                        )
CLIENT_SECRET_OAUTH = "{}/client_secret_oauth.json".format(
                            os.path.dirname(os.path.realpath(__file__))
                        )
TOKEN = "{}/token.json".format(
                            os.path.dirname(os.path.realpath(__file__))
                        )
SERVICE_ACCOUNT_CREDENTIALS = "{}/service_account_credentials.json".format(
                            os.path.dirname(os.path.realpath(__file__))
                        )
DELEGATED_EMAIL = "{}/delegated_email.txt".format(
                            os.path.dirname(os.path.realpath(__file__))
                        )


def build_service():
    """ Build service object to make calls to the Cloud Identity API using its
        Discovery URL """
    if(not os.path.exists(API_KEY_FILE)):
        exit("Please create a file with your API key at {}".format(API_KEY_FILE))

    # open/read the API key
    with open(API_KEY_FILE) as key_file:
        api_key = key_file.read().strip()
    
    # if service account credentials are found then use them
    # else look for oauth tokens
    if(os.path.exists(SERVICE_ACCOUNT_CREDENTIALS) and os.path.exists(DELEGATED_EMAIL)):
        credentials_without_domain_wide_delegation = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_CREDENTIALS, scopes=SCOPES)

        with open(DELEGATED_EMAIL) as email_file:
            delegated_email = email_file.read().strip()
        credentials = credentials_without_domain_wide_delegation.with_subject(delegated_email)
    else:
        if(not os.path.exists(CLIENT_SECRET_OAUTH)):
            exit("Please download your Oauth client file (client_secret_oauth.json).")
        if(not os.path.exists(TOKEN)):
            exit("Please run login.py to set up authentication")

        # get the token if it exists and rely on login.py to create token.json
        store = file.Storage(TOKEN)
        credentials = store.get()

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

@click.command('groups.create')
@click.option('--customer_id', required=True, help='Your customer ID.')
@click.option('--key', required=True, help=('Unique key for the group in email address format.'))
@click.option('--display_name', required=False, help=('A display name for the group.'))
@click.option('--description', required=False, help=('A description for the group.'))
def groups_create(customer_id, key, display_name, description):
    """Create a group.
    Args:
        service: service client.
        customer_id: your customer ID
        key: the group's key in email address format
        description: a description for the group
        display_name: a display name for the group
    Returns: the created group
    """
    service = build_service()
    groupDef = {
        "parent": "customerId/{}".format(customer_id),
        "groupKey": {"id": key},
        "description": description,
        "displayName": display_name,
        # the discussion_forum label is the only label currently supported
        "labels": {"system/groups/discussion_forum": ""}
    }

    try:
        request = service.groups().create(body=groupDef)
        request.uri += "&initialGroupConfig=WITH_INITIAL_OWNER"
        response = request.execute()
        # fetch the newly created group
        group = [service.groups().get(name=response['response']['name']).execute()]
        render(group)
    except Exception as e:
        render(e)

@click.command('groups.get')
@click.option('--name', required=False, help='The unique name identifier for the group. (This is not the group\'s display name)')
@click.option('--key', required=False, help=('Unique key for the group in email address format.'))
def groups_get(name, key):
    """Get a group by either name or key.

    Args:
        service: service client.
        name: the name of the group (i.e. groups/abcdefghijklmmnop
        key: id of the group in email format
    Returns: Group resource if found.
    """
    if(name is None and key is None):
        render(Exception('Either --name or --key are required.'))
        return

    service = build_service()
    try:
        # if id is passed we then we have to fetch the name
        if(name is None and key is not None):
            param = "&groupKey.id=" + key
            lookup_group_name_request = service.groups().lookup()
            lookup_group_name_request.uri += param
            lookup_group_name_response = lookup_group_name_request.execute()
            name = lookup_group_name_response.get("name")

        response = [service.groups().get(name=name).execute()]
        render(response)
    except Exception as e:
        render(e)

@click.command('groups.list')
@click.option('--customer_id', required=True, help='Your customer ID.')
@click.option('--page_size', required=False, default=10, help=('Number of groups to return.'))
def groups_list(customer_id, page_size):
    """List groups.

    Args:
        service: service client.
        customer_id: your customer ID
        page_size: page size for pagination.
        view: FULL / BASIC view of groups.
    Returns: List of groups.
    """
    service = build_service()
    search_query = urlencode({
            # this gets all groups in the customer the caller has permission to view with the discussion_forum label
            "query": "parent=='customerId/{}' && 'system/groups/discussion_forum' in labels".format(customer_id),
            "pageSize": page_size,
            "view": "BASIC"
        }
    )
    try:
        search_groups_request = service.groups().search()
        search_groups_request.uri += "&" + search_query
        groups = search_groups_request.execute()['groups']
        render(groups)
    except Exception as e:
        render(e)

@click.command('memberships.list')
@click.option('--name', required=True, help='The unique name identifier for the group. (This is not the group\'s display name)')
#@click.option('--key', required=False, help=('Unique key for the group in email address format.'))
def memberships_list(name):
    """List memberships of a group.

    Args:
        service: service client.
        name: name of the group (i.e. groups/abcdefghijklmnop)
    Returns: List of groups.
    """
    service = build_service()
    try:
        members_request = service.groups().memberships().list(parent=name)
        members_request.uri += "&view=FULL"
        members_response = members_request.execute()['memberships']
        # Only memberships with an expire time will return that field
        #   so we insert it for display purposes if it's not there
        if('expireTime' not in members_response[0].keys()):
            members_response[0]['expireTime'] = ''
        render(members_response)
    except Exception as e:
        render(e)

@click.command('memberships.get')
@click.option('--name', required=True, help='The unique name identifier for the membership. (This is not the member\'s display name)')
def memberships_get(name):
    """Get a membership.

    Args:
        service: service client.
        name: name of the membership (i.e. groups/abcdefghijklmnop/memberships/1234567890)
    Returns: Membership resource.
    """
    service = build_service()
    try:
        response = service.groups().memberships().get(
                name=name).execute()
        render([response])
    except Exception as e:
        render(e)

@click.command('memberships.create')
@click.option('--name', required=True, help='The unique name identifier for the group. (This is not the group\'s display name)')
@click.option('--member', required=True, help='The email address of the member to add. (Member resource must already exist)')
@click.option('--expiry', required=False, help='Expiration date/time for the membership as either a Unix timestamp or date string in the format "Nov 30 2019 23:59:59".')
def memberships_create(name, member, expiry):
    """Create group membership.

    Args:
        service: service client.
        name: name of the group the membership is being created in (i.e. groups/abcdefghijklmnop)
        member: email address of the member being created (i.e. user@domain.com or group@domain.com)
        expiry: unix timestamp or parsable time string (i.e. Nov 30 2019)
    Returns: Membership resource.
    """
    service = build_service()
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
        member = [service.groups().memberships().get(
                name=response['response']['name']).execute()]
        render(member)
    except Exception as e:
        render(e)

@click.command('memberships.expire')
@click.option('--name', required=True, help='The unique name identifier for the membership. (This is the full name i.e. groups/abc123/memmberships/789xyz)')
@click.option('--expiry', required=False, help='Expiration date/time for the membership as either a Unix timestamp or date string in the format "Nov 30 2019 23:59:59".')
def memberships_expire(name, expiry):
    """Set an expiration on a membership.

    Args:
        service: service client.
        name: name of the group the membership is being created in (i.e. groups/abcdefghijklmnop)
        member: email address of the member being created (i.e. user@domain.com or group@domain.com)
        expiry: unix timestamp or parsable time string (i.e. Nov 30 2019)
    Returns: Membership resource.
    """
    service = build_service()
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
        member = [service.groups().memberships().get(
                name=name).execute()]
        render(member)
    except Exception as e:
        render(e)

def get_expiry(expiry):
    """Convenience function to be able to parse a string into a timestamp"""
    if(re.search("^[0-9]+$", expiry)):
        return expiry
    else:
        return parse(expiry).strftime("%s")


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

@click.group()
def main():
    pass

main.add_command(groups_create)
main.add_command(groups_get)
main.add_command(groups_list)
main.add_command(memberships_list)
main.add_command(memberships_get)
main.add_command(memberships_create)
main.add_command(memberships_expire)

if __name__ == "__main__":
    main()
