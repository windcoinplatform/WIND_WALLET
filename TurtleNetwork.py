import json
import os
import sys

import pywaves as py
import requests
from flask import Flask, render_template, request, url_for, redirect, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

from python.Gateway import Gateway
from python.Token import Token
from python.User import User


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


FEE = 2000000

PORT = 4000

if getattr(sys, 'frozen', False):
    template_folder = resource_path('templates')
    static_folder = resource_path('static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    app = Flask(__name__)

app.secret_key = "TurtleNetwork"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
NODE = 'https://privatenode.blackturtle.eu'
py.setNode(NODE, 'TN', 'L')
py.setMatcher('https://privatematcher.blackturtle.eu')
gateways = []


def get_addr_gateway(url, addr):
    r = requests.get("https://" + url + ".blackturtle.eu/api/v1/coin-address/" + addr)
    return r.content.decode()


@login_manager.user_loader
def load_user(seed):
    return User(seed)


@app.route('/portfolio')
@login_required
def portfolio():
    result = requests.get(NODE + '/assets/balance/' + current_user.wallet.address)
    balances = json.loads(result.content)['balances']
    portfolio = []
    for balance in balances:
        asset = Token(balance['issueTransaction']['id'], balance['issueTransaction']['decimals'],
                      balance['balance'], balance['issueTransaction']['sender'],
                      balance['issueTransaction']['name'], balance['issueTransaction']['description'])
        portfolio.append(asset)
    return render_template('portfolio.html', portfolio=portfolio)


@app.route('/')
@login_required
def home():
    return render_template('home.html', address=current_user.wallet.address,
                           balance=float(current_user.wallet.balance()) / 10 ** 8, extra_fees=current_user.extra_fees/ 10 ** 8)


@app.route('/gateway/overview')
@login_required
def gateways_overview():
    return render_template('gateways.html', gateways=gateways)


@app.route('/lease/overview')
@login_required
def lease_overview():
    return render_template('lease.html', address=current_user.wallet.address)


@app.route('/gateway/<gateway>')
@login_required
def gateways_detail(gateway):
    gw: Gateway = next((x for x in gateways if x.name == gateway), None)
    index = gateways.index(gw)
    gw.set_personal_wallet(get_addr_gateway(gw.url, current_user.wallet.address))
    gateways[index] = gw
    return json.dumps(gw.__dict__)


@app.route('/gw/send/tn', methods=['POST'], strict_slashes=False)
@login_required
def gw_send_tn():
    data = request.data
    dataJ = json.loads(data.decode())
    dest = dataJ['addr']
    amount = float(dataJ['amount']) * (10 ** 8)
    gateway = py.Address(address=get_addr_gateway('gateway', dest))
    result = current_user.wallet.sendWaves(gateway, int(amount), txFee=FEE)
    return jsonify(result)


@app.route('/gw/send/<gateway>', methods=['POST'], strict_slashes=False)
@login_required
def gw_send_currencie(gateway):
    gw: Gateway = next((x for x in gateways if x.name == gateway), None)
    data = request.data
    gateway = py.Address(address=gw.general_addr)
    dataJ = json.loads(data.decode())
    print(dataJ)
    dest = dataJ['addr']
    amount = float(dataJ['amount']) * (10 ** 8)
    result = current_user.wallet.sendAsset(gateway, py.Asset(gw.assetId), int(amount), txFee=FEE, attachment=dest)
    return jsonify(result)


@app.route('/logout', methods=['GET'], strict_slashes=False)
@login_required
def do_logout():
    logout_user()
    gateways.clear()
    return login()


@app.route('/login', methods=['GET'], strict_slashes=False)
def login():
    return render_template('login.html')


@app.route('/assets/burn/<asset>', methods=['POST'], strict_slashes=False)
@login_required
def burn_asset(asset):
    pyAsset = py.Asset(assetId=asset)
    data = json.loads(request.data.decode())
    amount = float(data['amount']) * (10 ** pyAsset.decimals)
    burn = current_user.wallet.burnAsset(pyAsset, int(amount), txFee=FEE)
    return jsonify(burn)


@app.route('/tn/send/', methods=['POST'], strict_slashes=False)
@login_required
def send_tn():
    data = json.loads(request.data.decode())
    amount = float(data['amount']) * (10 ** 8)
    recipient = data['addr']
    attachment = data['attachment']
    send = current_user.wallet.sendWaves(py.Address(address=recipient), int(amount), attachment=attachment, txFee=FEE)
    return jsonify(send)


@app.route('/assets/send/<asset>', methods=['POST'], strict_slashes=False)
@login_required
def send_asset(asset):
    pyAsset = py.Asset(assetId=asset)
    data = json.loads(request.data.decode())
    addr = data['addr']
    amount = float(data['amount']) * (10 ** pyAsset.decimals)
    send = current_user.wallet.sendAsset(py.Address(addr), pyAsset, int(amount), txFee=FEE)
    return jsonify(send)


@app.route('/state/transactions/<addr>/<amount>')
def history_tx(addr, amount):
    r = requests.get(NODE + "/transactions/address/" + addr + "/limit/" + amount)
    return r.content.decode()


@app.route('/state/leases/<addr>')
def active_leasing(addr):
    r = requests.get(NODE + "/leasing/active/" + addr)
    return r.content.decode()


@app.route('/state/leases/cancel/<id>')
@login_required
def cancel_active_leasing(id):
    send = current_user.wallet.leaseCancel(leaseId=id, txFee=FEE)
    return jsonify(send)


@app.route('/state/leases/start', methods=['POST'], strict_slashes=False)
@login_required
def start_leasing():
    data = json.loads(request.data.decode())
    amount = float(data['amount']) * (10 ** 8)
    recipient = data['addr']
    send = current_user.wallet.lease(py.Address(address=recipient), int(amount), txFee=FEE)
    return jsonify(send)


@app.route('/details/<assetid>', strict_slashes=False)
@login_required
def details_asset(assetid):
    asset_details = py.Asset(assetId=assetid)
    if asset_details.decimals == 0:
        asset_balance = current_user.wallet.balance(assetId=assetid)
    else:
        asset_balance = current_user.wallet.balance(assetId=assetid) / asset_details.decimals
    asset_smart = asset_details.isSmart()
    return render_template('details.html', asset_details=asset_details, asset_balance=asset_balance,
                           asset_smart=asset_smart)


@app.route('/login', methods=['POST'], strict_slashes=False)
def do_admin_login():
    data = request.form
    seed = data['seed']
    pk = data['pk']
    login_user(User(pk, seed))
    gateways.append(
        Gateway('----------', '3JbpUeiV6BN9k2cMccKE5LZrrQ8wN44pxWy',
                0.01, 'waves', 'EzwaF58ssALcUCZ9FbyeD1GTSteoZAQZEDTqBAXHfq8y', 'wavesgateway'),
    )
    gateways.append(
        Gateway('----------', '3JnNnw91XQr3pDmpGWud9xGfz9hEF1hSTfG',
                0.006, 'litecoin', '3vB9hXHTCYbPiQNuyxCQgXF6AvFg51ozGKL9QkwoCwaS', 'litecoingw')
    )
    gateways.append(
        Gateway('----------', '3JeW3F1kEWxLsf8zg1uAZRPb7g5z6fuqEfF',
                0.001, 'bitcoin', '5Asy9P3xjcvBAgbeyiitZhBRJZJ2TPGSZJz9ihDTnB3d', 'bitcoingw'))
    gateways.append(
        Gateway('----------', '3JbigZzoGyFWksZ5RLuh9K5ntyGZuXKTVas',
                0.001, 'dash', 'A62sRG58HFbWUNvFoEEjX4U3txXKcLm11MXWWS429qpN', 'dashgw'))
    gateways.append(
        Gateway('----------', '3JsshGBTUXXqShXGQeNdtzw1EuQZFqxN4E3',
                0.03, 'wagerr', '91NnG9iyUs3ZT3tqK1oQ3ddpgAkE7v5Kbcgp2hhnDhqd', 'wagerrgw'))
    gateways.append(
        Gateway('----------', '3JiEjoFbgVKLVxdJYFD1HL9HYDN3RupVNHd',
                0.003, 'syscoin', 'HBxBjymrCC8TuL8rwCLr2vakDEq4obqkMwYYPEZtTauA', 'syscoingw'))
    gateways.append(
        Gateway('----------', '3JsenfjhSNRQsRZMXrkAtJMfjyzxrzSeCKr',
                0.0003, 'bitcoin cash', 'Fr2kNhe7XR3E16W7Mfh7NhNcsQWLXx3hSLjoFgpbFsNj', 'bchgw'))
    gateways.append(
        Gateway('----------', '3Jve26ckLkBivDbryLzpvoLyoRfxUaAE7tE',
                9, 'dogecoin', 'HDeemVktm2Z68RMkyA7AexhpaCqot1By7adBzaN9j5Xg', 'dogegw'))
    gateways.append(
        Gateway('----------', '3Jbrk85BjtVtEyrVLVVF7yWjKcnGPA6Rk5C',
                0.00041, 'ethereum', '6Mh41byVWPg8JVCfuwG5CAPCh9Q7gnuaAVxjDfVNDmcD', 'ethgw'))
    gateways.append(
        Gateway('----------', '33JgUZ2ytQicRQ1k38Y2nHeR9NxHK5fqEqbu',
                1, 'afin', 'A8jSBb33GztWpuCypUW9hJYPnTtJGZ7SDuSZfHCaeV49', 'afingw'))

    return redirect(url_for('home'))


def get_free_port():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    free_port = s.getsockname()[1]
    s.close()
    return free_port


PORT = get_free_port()


def run_server():
    app.run(host='127.0.0.1', port=PORT, threaded=True)


if __name__ == '__main__':
    run_server()

    # init_gui(app, window_title="Turtle Network Wallet", icon="static/favicon.ico")
