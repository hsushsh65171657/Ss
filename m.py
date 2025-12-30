from flask import Flask, request, jsonify
import asyncio
import aiohttp
import random
import json
import re
import time
import os
from datetime import datetime
import requests

app = Flask(__name__)

print("@S5llll")
print("="*60)

accounts_file = "accounts/accounts_data.json"
os.makedirs("accounts", exist_ok=True)

# ------------------------------
# دوال إدارة الحسابات
# ------------------------------

def load_accounts():
    if not os.path.exists(accounts_file):
        return []
    with open(accounts_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_accounts(accounts):
    with open(accounts_file, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def get_user_accounts(user_id):
    accounts = load_accounts()
    user_accs = [acc for acc in accounts if acc.get('user_id') == user_id]
    return user_accs

# ------------------------------
# دوال إنشاء البريد وحساب NanoBanana
# ------------------------------

async def create_email_account():
    email_url = "https://api.mail.tm"
    email_headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        async with aiohttp.ClientSession(headers=email_headers) as session:
            domains_resp = await session.get(f"{email_url}/domains")
            domains_data = await domains_resp.json()
            domain = domains_data["hydra:member"][0]["domain"]

            username = ''.join(random.choice("abcdefghijklmnopqrstuvwxyz1234567890") for _ in range(12))
            email = f"{username}@{domain}"
            password = f"Pass{random.randint(1000, 9999)}!"

            payload = {"address": email, "password": password}
            await session.post(f"{email_url}/accounts", json=payload)

            token_resp = await session.post(f"{email_url}/token", json=payload)
            token_data = await token_resp.json()
            token = token_data.get("token")

            print(f"✓ تم إنشاء البريد: {email}")
            return email, password, token

    except Exception as e:
        print(f"❌ خطأ في إنشاء البريد: {e}")
        return False, False, False

async def wait_for_verification_code(token, email):
    print(f"📭 جاري انتظار رمز التحقق في صندوق: {email}")
    headers = {"Authorization": f"Bearer {token}"}
    timeout = 300
    start_time = time.time()

    async with aiohttp.ClientSession(headers=headers) as session:
        while time.time() - start_time < timeout:
            try:
                messages_resp = await session.get("https://api.mail.tm/messages")
                inbox = await messages_resp.json()
                messages = inbox.get("hydra:member", [])

                for msg in messages:
                    sender = msg.get('from', {}).get('address', '')
                    if 'nanabanana.ai' in sender:
                        msg_id = msg["id"]
                        msg_resp = await session.get(f"https://api.mail.tm/messages/{msg_id}")
                        full_msg = await msg_resp.json()
                        text_content = full_msg.get('text', '')
                        matches = re.findall(r'\b\d{6}\b', text_content)
                        if matches:
                            code = matches[0]
                            print(f"✅ تم استقبال رمز التحقق: {code}")
                            return code
                await asyncio.sleep(5)
            except Exception as e:
                print(f"⚠ خطأ في التحقق من البريد: {e}")
                await asyncio.sleep(5)
    print("❌ انتهى وقت الانتظار ولم يتم استقبال الرمز")
    return None

async def create_nanabanana_account():
    email, password, mail_token = await create_email_account()
    if not email or not mail_token:
        return None, None, None
    # هنا يمكنك إضافة أي عملية تسجيل إضافية إذا تريد
    session_token = f"dummy_session_for_{email}"
    return email, password, session_token

def get_or_create_account(user_id):
    accounts = load_accounts()
    user_accs = [acc for acc in accounts if acc.get('user_id') == user_id]

    if user_accs:
        for acc in user_accs:
            if acc.get('use_count', 0) < 5:
                return acc
        for acc in user_accs:
            accounts.remove(acc)
        save_accounts(accounts)

    async def create_and_save():
        email, password, session_token = await create_nanabanana_account()
        if session_token:
            new_account = {
                'user_id': user_id,
                'email': email,
                'password': password,
                'session_token': session_token,
                'use_count': 0,
                'created_at': datetime.now().isoformat()
            }
            accounts.append(new_account)
            save_accounts(accounts)
            return new_account
        return None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(create_and_save())
    loop.close()
    return result

# ------------------------------
# API Endpoints
# ------------------------------

@app.route('/api/create_account', methods=['GET'])
def api_create_account():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id مطلوب'}), 400
    account = get_or_create_account(user_id)
    if account:
        return jsonify(account)
    return jsonify({'error': 'فشل في إنشاء الحساب'}), 500

# ------------------------------
# إنشاء صورة جديدة
# ------------------------------
@app.route('/api/create_image', methods=['POST'])
def api_create_image():
    data = request.json

    user_id = data.get('user_id')
    prompt = data.get('prompt')

    if not user_id or not prompt:
        return jsonify({'error': 'user_id و prompt مطلوبين'}), 400

    account = get_or_create_account(str(user_id))
    if not account:
        return jsonify({'error': 'فشل جلب الحساب'}), 500

    try:
        # نفس دالتك الحقيقية
        task_id = create_or_edit_image(
            account['session_token'],
            prompt
        )

        if not task_id:
            return jsonify({'error': 'فشل بدء المهمة'}), 500

        image_url = check_status(
            task_id,
            account['session_token']
        )

        if not image_url:
            return jsonify({'error': 'فشل إنشاء الصورة'}), 500

        # زيادة العداد
        accounts = load_accounts()
        for acc in accounts:
            if acc['session_token'] == account['session_token']:
                acc['use_count'] = acc.get('use_count', 0) + 1
                break
        save_accounts(accounts)

        return jsonify({
            'task_id': task_id,
            'image_url': image_url,
            'email': account['email']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ------------------------------
# تعديل صورة
# ------------------------------
@app.route('/api/edit_image', methods=['POST'])
def api_edit_image():
    data = request.json

    user_id = data.get('user_id')
    prompt = data.get('prompt')
    image_url = data.get('image_url')

    if not user_id or not prompt or not image_url:
        return jsonify({'error': 'user_id و prompt و image_url مطلوبين'}), 400

    account = get_or_create_account(str(user_id))
    if not account:
        return jsonify({'error': 'فشل جلب الحساب'}), 500

    try:
        # نفس دالتك الحقيقية
        task_id = create_or_edit_image(
            account['session_token'],
            prompt,
            [image_url]
        )

        if not task_id:
            return jsonify({'error': 'فشل بدء التعديل'}), 500

        image_result = check_status(
            task_id,
            account['session_token']
        )

        if not image_result:
            return jsonify({'error': 'فشل تعديل الصورة'}), 500

        # زيادة العداد
        accounts = load_accounts()
        for acc in accounts:
            if acc['session_token'] == account['session_token']:
                acc['use_count'] = acc.get('use_count', 0) + 1
                break
        save_accounts(accounts)

        return jsonify({
            'task_id': task_id,
            'image_url': image_result,
            'email': account['email']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ------------------------------
# تشغيل السيرفر
# ------------------------------

if __name__ == "__main__":
    print("🚀 Flask API شغال على http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000)
