from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
# from pydantic import BaseModel

# ----------------------------------------
#        Santa Data Types
# ----------------------------------------

#  Enums
class ClientMode(Enum):
    UNKNOWN_CLIENT_MODE = 0
    MONITOR = 1
    LOCKDOWN = 2
    STANDALONE = 3

class Decision(Enum):
    DECISION_UNKNOWN = 0
    ALLOW_UNKNOWN = 1
    ALLOW_BINARY = 2
    ALLOW_CERTIFICATE = 3
    ALLOW_SCOPE = 4
    ALLOW_TEAMID = 5
    ALLOW_SIGNINGID = 6
    ALLOW_CDHASH = 7
    BLOCK_UNKNOWN = 8
    BLOCK_BINARY = 9
    BLOCK_CERTIFICATE = 10
    BLOCK_SCOPE = 11
    BLOCK_TEAMID = 12
    BLOCK_SIGNINGID = 13
    BLOCK_CDHASH = 14
    BUNDLE_BINARY = 15

class FileAccessAction(Enum):
    FILE_ACCESS_ACTION_UNSPECIFIED = 0
    NONE = 1
    AUDIT_ONLY = 2
    DISABLE = 3

class Policy(Enum):
    POLICY_UNKNOWN = 0
    ALLOWLIST = 1
    ALLOWLIST_COMPILER = 2
    BLOCKLIST = 3
    SILENT_BLOCKLIST = 4
    REMOVE = 5
    CEL = 6

class RuleType(Enum):
    RULETYPE_UNKNOWN = 0
    BINARY = 1
    CERTIFICATE = 2
    TEAMID = 3
    SIGNINGID = 4
    CDHASH = 5

class SigningStatus(Enum):
    SIGNING_STATUS_UNSPECIFIED = 0
    SIGNING_STATUS_UNSIGNED = 1
    SIGNING_STATUS_INVALID = 2
    SIGNING_STATUS_ADHOC = 3
    SIGNING_STATUS_DEVELOPMENT = 4
    SIGNING_STATUS_PRODUCTION = 5

class SyncType(Enum):
    SYNC_TYPE_UNSPECIFIED = 0
    NORMAL = 1
    CLEAN = 2
    CLEAN_ALL = 3
    CLEAN_STANDALONE = 4
    CLEAN_RULES = 5

# Classes
@dataclass
class Certificate():
    sha256: str
    cn: str
    org: str
    ou: str
    valid_from: int
    valid_until: int

    def __post_init__(self):
        if ((not all(isinstance(i, str) for i in [self.sha256, self.cn, self.org, self.ou])) or 
            (not all(isinstance(i, int) for i in [self.valid_from, self.valid_until]))):
            raise Exception("Could not init Certificate, wrong data type given.")


@dataclass
class Entitlement ():
    key: str = None
    value: str = None

    def __post_init__(self):
        if (not all(isinstance(i, (str, type(None))) for i in [self.key, self.value])):
            raise Exception("Could not init Entitlement, wrong data type given.")

@dataclass
class EntitlementInfo():
    entitlements_filtered: bool = None
    entitlements = list[Entitlement]

    def __post_init__(self):
        self.entitlements = [Entitlement(**ent) for ent in self.entitlements]
        if not isinstance(self.entitlements_filtered, bool):
            raise Exception("Could not init EntitlementInfo, wrong data type given.")


@dataclass
class Event():
    file_sha256: str
    file_path: str
    file_name: str
    executing_user: str
    execution_time: float
    logged_in_users: list[str]
    current_sessions: list[str]
    decision: Decision
    file_bundle_id: str
    file_bundle_path: str
    file_bundle_executable_rel_path: str
    file_bundle_name: str
    file_bundle_version: str
    file_bundle_version_string: str
    file_bundle_hash: str
    file_bundle_hash_millis: int
    file_bundle_binary_count: int
    pid: int
    ppid: int
    parent_name: str
    team_id: str
    signing_id: str
    cdhash: str
    signing_chain: list[Certificate]
    entitlement_info: EntitlementInfo
    cs_flags: int
    signing_status: SigningStatus
    secure_signing_time: int
    signing_time: int
    static_rule: bool

    def __post_init__(self):
        self.decision = Decision(**self.decision)
        self.signing_chain = [Certificate(**cert) for cert in self.signing_chain]
        self.entitlement_info = EntitlementInfo(**self.entitlement_info)
        self.signing_status = SigningStatus(**self.signing_status)

        if ((not all(isinstance(i, str) for i in [self.file_sha256, self.file_path, self.file_name, self.executing_user, self.file_bundle_id, self.file_bundle_path, self.file_bundle_executable_rel_path, self.file_bundle_name, self.file_bundle_version, self.file_bundle_version_string, self.file_bundle_hash, self.parent_name, self.team_id, self.signing_id, self.cdhash])) or
            (not all(isinstance(i, int) for i in [self.file_bundle_hash_millis, self.file_bundle_binary_count, self.pid, self.ppid, self.cs_flags, self.secure_signing_time, self.signing_time])) or
            (not all(isinstance(i, list) for i in [self.logged_in_users, self.current_sessions])) or
            (not isinstance(self.execution_time, float))):
                raise Exception("Could not init Event, wrong data type given.")

@dataclass
class SignedPost():
    url: str
    form_values: dict[str, str]

    def __post_init__(self):
        if ((not all(isinstance(i, str) for i in [self.url])) or
            (not all(isinstance(i, dict[str, str]) for i in [self.form_values]))):
            raise Exception("Could not init SignedPost, wrong data type given.")

@dataclass
class ExportConfiguration():
    signed_post: SignedPost


@dataclass
class HostConfig():
    client_mode: ClientMode = None
    batch_size: int = None
    full_sync_interval: int = None
    push_notification_full_sync_interval: int = None
    push_notification_global_rule_sync_deadline: int = None
    block_usb_mount: bool = None
    remount_usb_mode: list[str] = None
    push_token: str = None
    push_issuer_token: str = None
    sync_type: SyncType = None
    enable_bundles: bool = None
    enable_transitive_rules: bool = None
    enable_all_event_upload: bool = None
    disable_unknown_event_upload: bool = None
    allowed_path_regex: str = None
    blocked_path_regex: str = None
    override_file_access_action: FileAccessAction = None
    export_configuration: ExportConfiguration = None
    event_detail_url: str = None
    event_detail_text: str = None


    def __post_init__(self):
        self.client_mode = ClientMode(**self.client_mode)
        if self.sync_type != None:
            self.sync_type = SyncType(**self.sync_type)
        if self.override_file_access_action != None:
            self.override_file_access_action = FileAccessAction(**self.override_file_access_action)
        if self.export_configuration != None:
            self.export_configuration = ExportConfiguration(**self.export_configuration)


        if ((not all(isinstance(i, str) for i in [self.push_token, self.push_issuer_token])) or
            (not all(isinstance(i, (str, type(None))) for i in [self.allowed_path_regex, self.blocked_path_regex, self.event_detail_url, self.event_detail_text])) or
            (not isinstance(self.remount_usb_mode, list)) or
            (not all(isinstance(i, int) for i in [self.batch_size, self.full_sync_interval, self.push_notification_full_sync_interval, self.push_notification_global_rule_sync_deadline])) or
            (not all(isinstance(i, bool) for i in [self.block_usb_mount])) or
            (not all(isinstance(i, (bool, type(None))) for i in [self.enable_bundles, self.enable_transitive_rules, self.enable_all_event_upload, self.disable_unknown_event_upload]))):
                raise Exception("Could not init Event, wrong data type given.")


@dataclass
class Rule():
    identifier: str
    policy: Policy
    rule_type: RuleType
    custom_msg: str = None
    custom_url: str = None
    notification_app_name: str = None
    cel_expr: str = None

    def __post_init__(self):
        self.policy = Policy(self.policy)
        self.rule_type = RuleType(self.rule_type)

        if ((not all(isinstance(i, str) for i in [self.identifier, self.custom_msg, self.custom_url, self.notification_app_name, self.cel_expr])) or
            (not all(isinstance(i, (str, type(None))) for i in [self.custom_msg, self.custom_url, self.notification_app_name, self.cel_expr]))):
            raise Exception("Could not init Rule, wrong data type given.")

        if self.policy == Policy.CEL:
            if cel_expr == None:
                raise Exception("Missing 1 required positional arguments, CEL policy requires fiels cel_expr.")

# ----------------------------------------
#       Krampus Classes
# ----------------------------------------
@dataclass
class EventSummary():
    file_name: str
    DECISION_UNKNOWN: int = None
    ALLOW_UNKNOWN: int = None
    ALLOW_BINARY: int = None
    ALLOW_CERTIFICATE: int = None
    ALLOW_SCOPE: int = None
    ALLOW_TEAMID: int = None
    ALLOW_SIGNINGID: int = None
    ALLOW_CDHASH: int = None
    BLOCK_UNKNOWN: int = None
    BLOCK_BINARY: int = None
    BLOCK_CERTIFICATE: int = None
    BLOCK_SCOPE: int = None
    BLOCK_TEAMID: int = None
    BLOCK_SIGNINGID: int = None
    BLOCK_CDHASH: int = None
    BUNDLE_BINARY: int = None

    def __post_init__(self):
        if ((not all(isinstance(i, str) for i in [self.file_name])) or
            (not all(isinstance(i, (int, type(None))) for i in [self.DECISION_UNKNOWN, self.ALLOW_UNKNOWN, self.ALLOW_BINARY, self.ALLOW_CERTIFICATE, self.ALLOW_SCOPE, self.ALLOW_TEAMID, self.ALLOW_SIGNINGID, self.ALLOW_CDHASH, self.BLOCK_UNKNOWN, self.BLOCK_BINARY, self.BLOCK_CERTIFICATE, self.BLOCK_SCOPE, self.BLOCK_TEAMID, self.BLOCK_SIGNINGID, self.BLOCK_CDHASH, self.BUNDLE_BINARY]))):
            raise Exception("Could not init EventSummary, wrong data type given.")


@dataclass
class MachineStatus():
    clean_sync_by: datetime
    n_rules_sent: int
    sync_type: SyncType
    last_check_in: datetime = None
    last_clean_sync: datetime = None

    def __post_init__(self):
        self.sync_type = SyncType(self.SyncType)

        if ((not all(isinstance(i, datetime) for i in [self.clean_sync_by])) or
            (not all(isinstance(i, (datetime, type(None))) for i in [self.last_check_in, self.last_clean_sync])) or
            (not all(isinstance(i, int) for i in [self.n_rules_sent]))):
            raise Exception("Could not init MachineStatus, wrong data type given.")

@dataclass
class KrampusRule(Rule):
    server_last_edit_date: datetime = datetime.now(timezone.utc)
    targets: list[str] = None
    exclusions: list[str] = None
    row_id: int = None

    def __post_init__(self):
        if ((not all(isinstance(i, (datetime, type(None))) for i in [self.server_last_edit_date])) or
            (not all(isinstance(i, (list, type(None))) for i in [self.targets, self.exclusions])) or
            (not all(isinstance(i, (int, type(None))) for i in [self.row_id]))):
            raise Exception("Could not init KrampusRule, wrong data type given.")

        if not self.targets:
            self.targets = ["all"]


@dataclass
class KrampusHostConfig(HostConfig):
    targets: list[str] = None
    exclusions: list[str] = None
    row_id: int = None

    def __post_init__(self):
        if (not all(isinstance(i, (list, type(None))) for i in [self.targets, self.exclusions])):
            raise Exception("Could not init KrampusHostConfig, wrong data type given.")

        if not self.targets:
            self.targets = ["all"]



# ----------------------------------------
#       Database Classes
# ----------------------------------------  

class DbRule():
    data: dict

    def __init__(self, data):
        self.data = data 

    def add(row_id: str=None) -> tuple[int, str]:
        '''
        Adds one row of data to the rules database, optionally at some specific row id.

        Parameters:
            collection: name of the collection to add data to
            data: data for that row in the collection
            row_id: desired id for new row in the collection

        Returns:
            int: http status code reflecting the success of the attempted action
            str: description of action taken
        '''
    pass
    

class DbHostConfig():
    data: dict

    def __init__(self, data):
        self.data = data 


class DbEventSummary():
    data: dict

    def __init__(self, data):
        self.data = data 

