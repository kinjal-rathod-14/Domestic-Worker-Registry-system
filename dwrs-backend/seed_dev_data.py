import asyncio
import asyncpg
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def seed():
    url = os.getenv('DATABASE_URL', '').replace('+asyncpg', '')
    if not url:
        print('ERROR: DATABASE_URL not set in .env')
        sys.exit(1)

    try:
        conn = await asyncpg.connect(url)
    except Exception as e:
        print(f'ERROR: Cannot connect to database: {e}')
        print('Make sure PostgreSQL is running and .env is configured correctly.')
        sys.exit(1)

    print('Connected to database...')

    # Insert test district
    await conn.execute("""
        INSERT INTO districts (id, name, state)
        VALUES ('00000000-0000-0000-0000-000000000001', 'Mumbai', 'Maharashtra')
        ON CONFLICT (id) DO NOTHING
    """)
    print('  District: Mumbai, Maharashtra - OK')

    # bcrypt hash of 'Test@1234'
    pw = r'$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGcOt8lv7MWMKZkIEzsBg7Rh8yq'

    # Insert test field officer
    await conn.execute(f"""
        INSERT INTO users (id, username, email, password_hash, role, district_id)
        VALUES (
            '00000000-0000-0000-0000-000000000010',
            'test_officer', 'officer@dwrs.test', '{pw}',
            'field_officer', '00000000-0000-0000-0000-000000000001'
        ) ON CONFLICT (id) DO NOTHING
    """)
    await conn.execute("""
        INSERT INTO officers (id, badge_number, district_id, trust_score)
        VALUES (
            '00000000-0000-0000-0000-000000000010',
            'OFF-001', '00000000-0000-0000-0000-000000000001', 1.000
        ) ON CONFLICT (id) DO NOTHING
    """)
    print('  User: test_officer (field_officer) - OK')

    # Insert test admin
    await conn.execute(f"""
        INSERT INTO users (id, username, email, password_hash, role)
        VALUES (
            '00000000-0000-0000-0000-000000000020',
            'test_admin', 'admin@dwrs.test', '{pw}', 'admin'
        ) ON CONFLICT (id) DO NOTHING
    """)
    print('  User: test_admin (admin) - OK')

    # Insert test worker user
    await conn.execute(f"""
        INSERT INTO users (id, username, email, password_hash, role)
        VALUES (
            '00000000-0000-0000-0000-000000000030',
            'test_worker', 'worker@dwrs.test', '{pw}', 'worker'
        ) ON CONFLICT (id) DO NOTHING
    """)
    print('  User: test_worker (worker) - OK')

    # Insert test supervisor
    await conn.execute(f"""
        INSERT INTO users (id, username, email, password_hash, role, district_id)
        VALUES (
            '00000000-0000-0000-0000-000000000040',
            'test_supervisor', 'supervisor@dwrs.test', '{pw}',
            'supervisor', '00000000-0000-0000-0000-000000000001'
        ) ON CONFLICT (id) DO NOTHING
    """)
    print('  User: test_supervisor (supervisor) - OK')

    await conn.close()
    print('')
    print('Seed complete! Test credentials:')
    print('  Username: test_officer   Password: Test@1234  Role: field_officer')
    print('  Username: test_admin     Password: Test@1234  Role: admin')
    print('  Username: test_worker    Password: Test@1234  Role: worker')
    print('  Username: test_supervisor Password: Test@1234 Role: supervisor')

asyncio.run(seed())
