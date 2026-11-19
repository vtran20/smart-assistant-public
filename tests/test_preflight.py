"""Preflight must not confuse observed tools with permission."""
import unittest
from smart_assistant.contracts import (
    ActionKind, HostDecision, RequestedAction, AuthorizationScope, ValidationError,
)
from smart_assistant.preflight import preflight


class PreflightTests(unittest.TestCase):
    def action(self, host=HostDecision.ALLOWED, tool='mail'):
        return RequestedAction('send', ActionKind.EXTERNAL_WRITE, 'recipient:a', tool, host)

    def scope(self, kind=ActionKind.EXTERNAL_WRITE, destination='recipient:a'):
        return AuthorizationScope(kind, destination, 'user:request')

    def test_exact_scope_allowed_host_and_observed_tools_are_ready(self):
        result = preflight({'review'}, {'review', 'mail'}, [self.action()], [self.scope()])
        self.assertTrue(result.ready)
        self.assertEqual(result.pending_actions, [])

    def test_tools_alone_never_authorize(self):
        result = preflight(set(), {'mail'}, [self.action()], [])
        self.assertFalse(result.ready)
        self.assertEqual([p.action_ref for p in result.pending_actions], ['send'])
        self.assertIn('authorization', result.pending_actions[0].reason)

    def test_scope_requires_exact_kind_and_destination(self):
        for scope in [self.scope(destination='recipient:*'), self.scope(destination='recipient:'),
                      self.scope(destination='recipient:b'), self.scope(kind=ActionKind.EXTERNAL_READ)]:
            with self.subTest(scope=scope):
                self.assertFalse(preflight(set(), {'mail'}, [self.action()], [scope]).ready)

    def test_each_nonalallowed_host_remains_pending_even_when_authorized(self):
        for host in [HostDecision.DENIED, HostDecision.UNKNOWN, HostDecision.APPROVAL_REQUIRED]:
            with self.subTest(host=host):
                result = preflight(set(), {'mail'}, [self.action(host)], [self.scope()])
                self.assertFalse(result.ready)
                self.assertIn(host.value, result.pending_actions[0].reason)

    def test_missing_workflow_and_action_tools_are_sorted(self):
        result = preflight({'z-tool', 'a-tool'}, set(), [self.action()], [self.scope()])
        self.assertEqual(result.missing_tools, ['a-tool', 'mail', 'z-tool'])
        self.assertFalse(result.ready)
        self.assertIn('mail', result.pending_actions[0].reason)

    def test_action_without_required_tool_can_be_ready(self):
        self.assertTrue(preflight(set(), set(), [self.action(tool=None)], [self.scope()]).ready)

    def test_empty_workflow_is_ready_and_does_not_execute(self):
        self.assertTrue(preflight(set(), set(), [], []).ready)

    def test_malformed_inputs_raise_validation_error(self):
        for args in [([], set(), [], []), ({''}, set(), [], []), (set(), {' '}, [], []),
                     (set(), set(), [None], []), (set(), set(), [], [None]),
                     (set(), set(), (), [])]:
            with self.subTest(args=args), self.assertRaises(ValidationError):
                preflight(*args)

    def test_duplicate_action_references_reject_ambiguous_pending_results(self):
        with self.assertRaises(ValidationError):
            preflight(set(), set(), [self.action(), self.action()], [])

    def test_raw_valid_host_decision_strings_preserve_policy_and_inputs(self):
        import copy
        for host, ready in [('allowed', True), ('denied', False),
                            ('unknown', False), ('approval_required', False)]:
            action = self.action()
            action.host_decision = host
            actions = [action]
            scopes = [self.scope()]
            before = copy.deepcopy((actions, scopes))
            with self.subTest(host=host):
                result = preflight(set(), {'mail'}, actions, scopes)
                self.assertEqual(result.ready, ready)
                self.assertEqual((actions, scopes), before)
                if not ready:
                    self.assertEqual([pending.action_ref for pending in result.pending_actions], ['send'])
                    self.assertIn(host, result.pending_actions[0].reason)

    def test_raw_action_and_scope_kinds_match_exactly_without_mutation(self):
        import copy
        action = self.action()
        action.kind = 'external_write'
        for kind, ready in [('external_write', True), ('external_read', False)]:
            scope = self.scope()
            scope.action_kind = kind
            before = copy.deepcopy((action, scope))
            with self.subTest(kind=kind):
                self.assertEqual(preflight(set(), {'mail'}, [action], [scope]).ready, ready)
                self.assertEqual((action, scope), before)

    def test_invalid_raw_enum_strings_reject_through_validation_error(self):
        for field, value in [('host_decision', 'unrecognized'), ('kind', 'execute')]:
            action = self.action()
            setattr(action, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                preflight(set(), {'mail'}, [action], [self.scope()])
