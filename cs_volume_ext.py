#!/usr/bin/python

import base64
import urllib2
import urllib
import json
import hmac
import hashlib
import re

# import cloudstack common
from ansible.module_utils.cloudstack import *

class BaseClient(object):
    def __init__(self, api, apikey, secret):
        self.api = api
        self.apikey = apikey
        self.secret = secret

    def request(self, command, args):
        args['apikey']   = self.apikey
        args['command']  = command
        args['response'] = 'json'

        params=[]

        keys = sorted(args.keys())

        for k in keys:
            params.append(k + '=' + urllib.quote_plus(args[k]).replace("+", "%20"))

        query = '&'.join(params)

        signature = base64.b64encode(hmac.new(
            self.secret,
            msg=query.lower(),
            digestmod=hashlib.sha1
        ).digest())

        query += '&signature=' + urllib.quote_plus(signature)

        try:
            response = urllib2.urlopen(self.api + '?' + query)
        except urllib2.HTTPError as error:
            error_msg = ''
            error_data = json.loads(error.read())
            if len(error_data) == 1:
                error_msg = 'ERROR: %s - %s' % (error_data.keys()[0],error_data[error_data.keys()[0]]['errortext'])
            else:
                error_msg = 'ERROR: Recieved muliaple errors.'
            raise RuntimeError(error_msg)

        decoded = json.loads(response.read())

        propertyResponse = command.lower() + 'response'
        if not propertyResponse in decoded:
            if 'errorresponse' in decoded:
                raise RuntimeError("ERROR: " + decoded['errorresponse']['errortext'])
            else:
                raise RuntimeError("ERROR: Unable to parse the response")

        response = decoded[propertyResponse]
        result = re.compile(r"^list(\w+)s").match(command.lower())

        if not result is None:
            type = result.group(1)

            if type in response:
                return response[type]
            else:
                # sometimes, the 's' is kept, as in :
                # { "listasyncjobsresponse" : { "asyncjobs" : [ ... ] } }
                type += 's'
                if type in response:
                    return response[type]

        return response

def main():

    fields = {
        "display_name": {"required": True, "type": "str"},
        "disk_size": {"required": True, "type": "str"},
    }

    module = AnsibleModule(argument_spec=fields)
    
    acs_instance = AnsibleCloudStack(module)

    api_config = {
      'api': acs_instance.cs.endpoint,
      'apikey': acs_instance.cs.key,
      'secret': acs_instance.cs.secret,
    }

    bc = BaseClient(**api_config)

    instances = bc.request('listVirtualMachines', {})
    for v in instances:
      if module.params['display_name'].lower() in [v['name'].lower(), v['displayname'].lower(), v['id']]:
        instance = v
        break

    instanceid = instance['id']
    args={'virtualmachineid':instanceid}
    volume=bc.request('listVolumes', args)[0]

    vsize=volume['size']/(1024*1024*1024)
    vid=volume['id']

    changed = False
    response = {}
    if (vsize + 5) < module.params['disk_size']:
      changed = True
      args={
        'id':vid, 
        'size':module.params['disk_size']
      }
      response=bc.request('resizeVolume', args)

    module.exit_json(changed=changed, meta=response)

from ansible.module_utils.basic import *
if __name__ == '__main__':  
    main()
