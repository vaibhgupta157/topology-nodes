# -*- mode: python; python-indent: 4 -*-
import ncs
#import ncs.maapi as maapi
#import ncs.maagic as maagic
import _ncs
from ncs.application import Service, PlanComponent
import resource_manager.ipaddress_allocator as ip_allocator

AS_No = 65000


def check_device(service):
    with ncs.maapi.single_write_trans('admin', 'admin', groups=['ncsadmin']) as t:
        root = ncs.maagic.get_root(t)
        if service.name in root.devices.device.keys():
            t.apply()
            return True
        else:
            t.apply()
            return False

# ------------------------
# SERVICE CALLBACK EXAMPLE
# ------------------------
class ServiceCallbacks(Service):

    # The create() callback is invoked inside NCS FASTMAP and
    # must always exist.
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info('Service create(service=', service._path, ')')
        plan = PlanComponent(service, "self", "ncs:self")
        plan.append_state("ncs:init")
        plan.append_state("topology-nodes:device-onboarding")
        plan.append_state("topology-nodes:fetch-sshkey")
        plan.append_state("topology-nodes:sync-from")
        plan.append_state("topology-nodes:day0-config")
        plan.append_state("ncs:ready")

        plan.set_reached("ncs:init")

        template = ncs.template.Template(service)

        try:
            template.apply('onboarding-node')
        except Exception as e:
            self.log.error("Onboarding node failed : " + str(e))
            plan.set_failed("topology-nodes:device-onboarding")
            return

        if not check_device(service):
            template.apply('device-onboarding-kicker')
            return

        plan.set_reached("topology-nodes:device-onboarding")

        try:
            with ncs.maapi.single_write_trans('admin', 'admin', groups=['ncsadmin']) as t:
                root = ncs.maagic.get_root(t)
                device = root.devices.device[service.name]
                output = device.ssh.fetch_host_keys()
                self.log.info('[{}]fetch result: {}'.format(service.name, output.result))
                t.apply()
        except Exception as e:
            self.log.error("Fetching ssh key failed : " + str(e))
            plan.set_failed("topology-nodes:fetch-sshkey")
            return

        plan.set_reached("topology-nodes:fetch-sshkey")

        try:
            with ncs.maapi.single_write_trans('admin', 'admin', groups=['ncsadmin']) as t:
                root = ncs.maagic.get_root(t)
                device = root.devices.device[service.name]
                output = device.sync_from()
                self.log.info('Sync-from result: {}'.format(output.result))
                t.apply()
        except Exception as e:
            self.log.error("Sync-From failed : " + str(e))
            plan.set_failed("topology-nodes:sync-from")
            return

        plan.set_reached("topology-nodes:sync-from") 

        pool_name = "deviceLoopbacks"
        allocation_name = service.name + "Loopback"

        ip_allocator.net_request(service,
                             "/topology-nodes:topology-nodes[name='%s']" % (service.name),
                             tctx.username,
                             pool_name,
                             allocation_name,
                             32)

        loopback_ip = ip_allocator.net_read(tctx.username, root,
                               pool_name, allocation_name)
        if not loopback_ip:
            self.log.info("Alloc not ready")
            return


        vars = ncs.template.Variables()
        vars.add('loopback_ip', loopback_ip)
        vars.add('ASN', AS_No)
        template = ncs.template.Template(service)
        template.apply('day0-config', vars)

        plan.set_reached("topology-nodes:day0-config")
        plan.set_reached("ncs:ready")


    # The pre_modification() and post_modification() callbacks are optional,
    # and are invoked outside FASTMAP. pre_modification() is invoked before
    # create, update, or delete of the service, as indicated by the enum
    # ncs_service_operation op parameter. Conversely
    # post_modification() is invoked after create, update, or delete
    # of the service. These functions can be useful e.g. for
    # allocations that should be stored and existing also when the
    # service instance is removed.

    # @Service.pre_lock_create
    # def cb_pre_lock_create(self, tctx, root, service, proplist):
    #     self.log.info('Service plcreate(service=', service._path, ')')

    # @Service.pre_modification
    # def cb_pre_modification(self, tctx, op, kp, root, proplist):
    #     self.log.info('Service premod(service=', kp, ')')

    # @Service.post_modification
    # def cb_post_modification(self, tctx, op, kp, root, proplist):
    #     self.log.info('Service premod(service=', kp, ')')


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(ncs.application.Application):
    def setup(self):
        # The application class sets up logging for us. It is accessible
        # through 'self.log' and is a ncs.log.Log instance.
        self.log.info('Main RUNNING')

        # Service callbacks require a registration for a 'service point',
        # as specified in the corresponding data model.
        #
        self.register_service('topology-nodes-servicepoint', ServiceCallbacks)

        # If we registered any callback(s) above, the Application class
        # took care of creating a daemon (related to the service/action point).

        # When this setup method is finished, all registrations are
        # considered done and the application is 'started'.

    def teardown(self):
        # When the application is finished (which would happen if NCS went
        # down, packages were reloaded or some error occurred) this teardown
        # method will be called.

        self.log.info('Main FINISHED')
