from sqlalchemy.orm import Session

from app.core.auth import hash_password
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole
from app.core.config import settings


ADMIN_ROLE_CODE = "ADMIN"
ADMIN_ROLE_NAME = "관리자"
VENDOR_PORTAL_ROLE_CODE = "VENDOR_PORTAL"
VENDOR_PORTAL_ROLE_NAME = "외주업체 포털"


ADMIN_USER_NAME = "관리자"

WEAK_ADMIN_PASSWORDS = {
    "admin",
    "admin1",
    "password",
    "123456",
    "12345678",
    "qwerty",
}

PERMISSION_SEEDS = [
    {
        "permission_code": "USERS.VIEW",
        "menu_code": "USERS",
        "action_code": "VIEW",
        "permission_name": "회원관리 조회",
        "sort_order": 100,
    },
    {
        "permission_code": "USERS.CREATE",
        "menu_code": "USERS",
        "action_code": "CREATE",
        "permission_name": "회원관리 등록",
        "sort_order": 110,
    },
    {
        "permission_code": "USERS.UPDATE",
        "menu_code": "USERS",
        "action_code": "UPDATE",
        "permission_name": "회원관리 수정",
        "sort_order": 120,
    },
    {
        "permission_code": "USERS.DELETE",
        "menu_code": "USERS",
        "action_code": "DELETE",
        "permission_name": "회원관리 삭제",
        "sort_order": 130,
    },
    {
        "permission_code": "USERS.RESET_PASSWORD",
        "menu_code": "USERS",
        "action_code": "RESET_PASSWORD",
        "permission_name": "회원 비밀번호 초기화",
        "sort_order": 140,
    },
    {
        "permission_code": "ROLES.VIEW",
        "menu_code": "ROLES",
        "action_code": "VIEW",
        "permission_name": "역할관리 조회",
        "sort_order": 200,
    },
    {
        "permission_code": "ROLES.CREATE",
        "menu_code": "ROLES",
        "action_code": "CREATE",
        "permission_name": "역할관리 등록",
        "sort_order": 210,
    },
    {
        "permission_code": "ROLES.UPDATE",
        "menu_code": "ROLES",
        "action_code": "UPDATE",
        "permission_name": "역할관리 수정",
        "sort_order": 220,
    },
    {
        "permission_code": "ROLES.DELETE",
        "menu_code": "ROLES",
        "action_code": "DELETE",
        "permission_name": "역할관리 삭제",
        "sort_order": 230,
    },
    {
        "permission_code": "PERMISSIONS.VIEW",
        "menu_code": "PERMISSIONS",
        "action_code": "VIEW",
        "permission_name": "권한목록 조회",
        "sort_order": 300,
    },
    {
        "permission_code": "ROLE_PERMISSIONS.VIEW",
        "menu_code": "ROLE_PERMISSIONS",
        "action_code": "VIEW",
        "permission_name": "역할 권한 조회",
        "sort_order": 400,
    },
    {
        "permission_code": "ROLE_PERMISSIONS.UPDATE",
        "menu_code": "ROLE_PERMISSIONS",
        "action_code": "UPDATE",
        "permission_name": "역할 권한 수정",
        "sort_order": 410,
    },
        {
        "permission_code": "DASHBOARD.VIEW",
        "menu_code": "DASHBOARD",
        "action_code": "VIEW",
        "permission_name": "대시보드 조회",
        "sort_order": 10,
    },
    {
        "permission_code": "DEFECT_TYPES.VIEW",
        "menu_code": "DEFECT_TYPES",
        "action_code": "VIEW",
        "permission_name": "불량유형 관리 조회",
        "sort_order": 1000,
    },
    {
        "permission_code": "PROCESSES.VIEW",
        "menu_code": "PROCESSES",
        "action_code": "VIEW",
        "permission_name": "공정 관리 조회",
        "sort_order": 1010,
    },
    {
        "permission_code": "PARTNERS.VIEW",
        "menu_code": "PARTNERS",
        "action_code": "VIEW",
        "permission_name": "거래처 관리 조회",
        "sort_order": 1020,
    },
    {
        "permission_code": "ROUTING_TEMPLATES.VIEW",
        "menu_code": "ROUTING_TEMPLATES",
        "action_code": "VIEW",
        "permission_name": "라우팅 템플릿 관리 조회",
        "sort_order": 1030,
    },
    {
        "permission_code": "ROUTING_TEMPLATE_STEPS.VIEW",
        "menu_code": "ROUTING_TEMPLATE_STEPS",
        "action_code": "VIEW",
        "permission_name": "라우팅 Step 관리 조회",
        "sort_order": 1040,
    },
    {
        "permission_code": "DRAWINGS.VIEW",
        "menu_code": "DRAWINGS",
        "action_code": "VIEW",
        "permission_name": "도면 관리 조회",
        "sort_order": 1050,
    },
    {
        "permission_code": "PRODUCTS.VIEW",
        "menu_code": "PRODUCTS",
        "action_code": "VIEW",
        "permission_name": "품목 관리 조회",
        "sort_order": 1060,
    },
    {
        "permission_code": "ORDER_LINE_CREATE.VIEW",
        "menu_code": "ORDER_LINE_CREATE",
        "action_code": "VIEW",
        "permission_name": "수주 등록 조회",
        "sort_order": 2000,
    },
    {
        "permission_code": "ORDER_LINE_LIST.VIEW",
        "menu_code": "ORDER_LINE_LIST",
        "action_code": "VIEW",
        "permission_name": "발주리스트 조회",
        "sort_order": 2010,
    },
    {
        "permission_code": "LOTS.VIEW",
        "menu_code": "LOTS",
        "action_code": "VIEW",
        "permission_name": "LOT 공정관리 조회",
        "sort_order": 3000,
    },
    {
        "permission_code": "PRODUCTION_DAILY.VIEW",
        "menu_code": "PRODUCTION_DAILY",
        "action_code": "VIEW",
        "permission_name": "생산진행현황 조회",
        "sort_order": 3010,
    },
    {
        "permission_code": "INSPECTION_WORK_INSTRUCTIONS.VIEW",
        "menu_code": "INSPECTION_WORK_INSTRUCTIONS",
        "action_code": "VIEW",
        "permission_name": "검수 작업지시 조회",
        "sort_order": 4000,
    },
    {
        "permission_code": "INSPECTION_SCHEDULES.VIEW",
        "menu_code": "INSPECTION_SCHEDULES",
        "action_code": "VIEW",
        "permission_name": "검수 스케줄 관리 조회",
        "sort_order": 4010,
    },
    {
        "permission_code": "INSPECTION_RESULTS.VIEW",
        "menu_code": "INSPECTION_RESULTS",
        "action_code": "VIEW",
        "permission_name": "검수실적관리 조회",
        "sort_order": 4020,
    },
    {
        "permission_code": "OUTSOURCE_WORK_INSTRUCTIONS.VIEW",
        "menu_code": "OUTSOURCE_WORK_INSTRUCTIONS",
        "action_code": "VIEW",
        "permission_name": "외주 작업지시 조회",
        "sort_order": 5000,
    },
    {
        "permission_code": "OUTSOURCE_PURCHASE_ORDERS.VIEW",
        "menu_code": "OUTSOURCE_PURCHASE_ORDERS",
        "action_code": "VIEW",
        "permission_name": "외주 발주서 작성 조회",
        "sort_order": 5010,
    },
    {
        "permission_code": "OUTSOURCE_PURCHASE_ORDER_LIST.VIEW",
        "menu_code": "OUTSOURCE_PURCHASE_ORDER_LIST",
        "action_code": "VIEW",
        "permission_name": "외주발주 리스트 조회",
        "sort_order": 5020,
    },
    {
        "permission_code": "BOHYUN_OUTSOURCE_MANAGEMENT.VIEW",
        "menu_code": "BOHYUN_OUTSOURCE_MANAGEMENT",
        "action_code": "VIEW",
        "permission_name": "보현문화 외주관리 조회",
        "sort_order": 5030,
    },
    {
        "permission_code": "BOHYUN_OUTSOURCE_SHIPMENT_LIST.VIEW",
        "menu_code": "BOHYUN_OUTSOURCE_SHIPMENT_LIST",
        "action_code": "VIEW",
        "permission_name": "보현문화 출고리스트 조회",
        "sort_order": 5040,
    },
    {
        "permission_code": "OUTSOURCE_PROCESSING_COSTS.VIEW",
        "menu_code": "OUTSOURCE_PROCESSING_COSTS",
        "action_code": "VIEW",
        "permission_name": "외주가공비 관리 조회",
        "sort_order": 5050,
    },
    {
        "permission_code": "PRODUCT_MONITORING.VIEW",
        "menu_code": "PRODUCT_MONITORING",
        "action_code": "VIEW",
        "permission_name": "품목 모니터링 조회",
        "sort_order": 6000,
    },
    {
        "permission_code": "INVENTORIES.VIEW",
        "menu_code": "INVENTORIES",
        "action_code": "VIEW",
        "permission_name": "재고 관리 조회",
        "sort_order": 7000,
    },
    {
        "permission_code": "SHIPMENTS.VIEW",
        "menu_code": "SHIPMENTS",
        "action_code": "VIEW",
        "permission_name": "출하 관리 조회",
        "sort_order": 8000,
    },

    {
    "permission_code": "DEFECT_TYPES.WRITE",
    "menu_code": "DEFECT_TYPES",
    "action_code": "WRITE",
    "permission_name": "불량유형 관리 저장",
    "sort_order": 1001,
    },
    {
        "permission_code": "PROCESSES.WRITE",
        "menu_code": "PROCESSES",
        "action_code": "WRITE",
        "permission_name": "공정 관리 저장",
        "sort_order": 1011,
    },
    {
        "permission_code": "PARTNERS.WRITE",
        "menu_code": "PARTNERS",
        "action_code": "WRITE",
        "permission_name": "거래처 관리 저장",
        "sort_order": 1021,
    },
    {
        "permission_code": "ROUTING_TEMPLATES.WRITE",
        "menu_code": "ROUTING_TEMPLATES",
        "action_code": "WRITE",
        "permission_name": "라우팅 템플릿 관리 저장",
        "sort_order": 1031,
    },
    {
        "permission_code": "DRAWINGS.WRITE",
        "menu_code": "DRAWINGS",
        "action_code": "WRITE",
        "permission_name": "도면 관리 저장",
        "sort_order": 1051,
    },
    {
        "permission_code": "PRODUCTS.WRITE",
        "menu_code": "PRODUCTS",
        "action_code": "WRITE",
        "permission_name": "품목 관리 저장",
        "sort_order": 1061,
    },
    {
        "permission_code": "ORDER_LINES.WRITE",
        "menu_code": "ORDER_LINES",
        "action_code": "WRITE",
        "permission_name": "수주 관리 저장",
        "sort_order": 2011,
    },
    {
        "permission_code": "LOTS.WRITE",
        "menu_code": "LOTS",
        "action_code": "WRITE",
        "permission_name": "LOT 공정관리 저장",
        "sort_order": 3001,
    },
    {
        "permission_code": "INSPECTIONS.WRITE",
        "menu_code": "INSPECTIONS",
        "action_code": "WRITE",
        "permission_name": "검수 관리 저장",
        "sort_order": 4011,
    },
    {
        "permission_code": "OUTSOURCE_WORK_INSTRUCTIONS.WRITE",
        "menu_code": "OUTSOURCE_WORK_INSTRUCTIONS",
        "action_code": "WRITE",
        "permission_name": "외주 작업관리 저장",
        "sort_order": 5001,
    },
    {
        "permission_code": "OUTSOURCE_PROCESSING_COSTS.WRITE",
        "menu_code": "OUTSOURCE_PROCESSING_COSTS",
        "action_code": "WRITE",
        "permission_name": "외주가공비 관리 저장",
        "sort_order": 5051,
    },
    {
        "permission_code": "INVENTORIES.WRITE",
        "menu_code": "INVENTORIES",
        "action_code": "WRITE",
        "permission_name": "재고 관리 저장",
        "sort_order": 7001,
    },
    {
        "permission_code": "SHIPMENTS.WRITE",
        "menu_code": "SHIPMENTS",
        "action_code": "WRITE",
        "permission_name": "출하 관리 저장",
        "sort_order": 8001,
    },
]


def ensure_auth_seed_data(db: Session) -> None:
    try:
        admin_role = _ensure_admin_role(db)
        _ensure_vendor_portal_role(db)
        _ensure_permissions(db)

        admin_user = _ensure_admin_user(db)

        db.flush()

        _ensure_user_role(db, admin_user.user_id, admin_role.role_id)
        _ensure_admin_permissions(db, admin_role.role_id)

        db.commit()
    except Exception:
        db.rollback()
        raise


def _ensure_admin_role(db: Session) -> Role:
    role = db.query(Role).filter(Role.role_code == ADMIN_ROLE_CODE).first()

    if role is None:
        role = Role(
            role_code=ADMIN_ROLE_CODE,
            role_name=ADMIN_ROLE_NAME,
            description="시스템 최초 관리자 역할",
            is_system=True,
            is_active=True,
        )
        db.add(role)
        db.flush()
        return role

    role.role_name = ADMIN_ROLE_NAME
    role.is_system = True
    role.is_active = True

    return role


def _ensure_vendor_portal_role(db: Session) -> Role:
    role = db.query(Role).filter(Role.role_code == VENDOR_PORTAL_ROLE_CODE).first()

    if role is None:
        role = Role(
            role_code=VENDOR_PORTAL_ROLE_CODE,
            role_name=VENDOR_PORTAL_ROLE_NAME,
            description="외주업체 전용 WPF 로그인 계정 역할",
            is_system=True,
            is_active=True,
        )
        db.add(role)
        db.flush()
        return role

    role.role_name = VENDOR_PORTAL_ROLE_NAME
    role.description = "외주업체 전용 WPF 로그인 계정 역할"
    role.is_system = True
    role.is_active = True

    return role


def _ensure_admin_user(db: Session) -> User:
    admin_login_id = settings.MES_ADMIN_LOGIN_ID.strip()

    user = db.query(User).filter(User.login_id == admin_login_id).first()
    if user is not None:
        return user

    admin_password = settings.MES_ADMIN_PASSWORD

    if admin_password is None or not admin_password.strip():
        raise RuntimeError(
            "최초 관리자 계정 생성을 위해 MES_ADMIN_PASSWORD를 .env에 설정해야 합니다."
        )

    admin_password = admin_password.strip()
    _validate_admin_password(admin_password)

    user = User(
        login_id=admin_login_id,
        user_name=ADMIN_USER_NAME,
        password_hash=hash_password(admin_password),
        department=None,
        position=None,
        is_active=True,
    )

    db.add(user)
    db.flush()

    return user

def _validate_admin_password(password: str) -> None:
    normalized = password.strip().lower()

    if len(password) < 12:
        raise RuntimeError(
            "MES_ADMIN_PASSWORD는 최소 12자 이상이어야 합니다."
        )

    if normalized in WEAK_ADMIN_PASSWORDS:
        raise RuntimeError(
            "MES_ADMIN_PASSWORD가 너무 약합니다. 다른 비밀번호를 사용하세요."
        )

def _ensure_permissions(db: Session) -> None:
    for seed in PERMISSION_SEEDS:
        permission = (
            db.query(Permission)
            .filter(Permission.permission_code == seed["permission_code"])
            .first()
        )

        if permission is None:
            permission = Permission(
                permission_code=seed["permission_code"],
                menu_code=seed["menu_code"],
                action_code=seed["action_code"],
                permission_name=seed["permission_name"],
                sort_order=seed["sort_order"],
                is_active=True,
            )
            db.add(permission)
            continue

        permission.menu_code = seed["menu_code"]
        permission.action_code = seed["action_code"]
        permission.permission_name = seed["permission_name"]
        permission.sort_order = seed["sort_order"]
        permission.is_active = True

    db.flush()


def _ensure_user_role(db: Session, user_id: int, role_id: int) -> None:
    exists = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
        .first()
    )

    if exists is not None:
        return

    db.add(
        UserRole(
            user_id=user_id,
            role_id=role_id,
        )
    )

    db.flush()


def _ensure_admin_permissions(db: Session, role_id: int) -> None:
    permissions = db.query(Permission).filter(Permission.is_active == True).all()

    existing_permission_ids = {
        row.permission_id
        for row in db.query(RolePermission)
        .filter(RolePermission.role_id == role_id)
        .all()
    }

    for permission in permissions:
        if permission.permission_id in existing_permission_ids:
            continue

        db.add(
            RolePermission(
                role_id=role_id,
                permission_id=permission.permission_id,
            )
        )

    db.flush()
