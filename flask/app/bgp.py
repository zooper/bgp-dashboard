from flask import Flask, jsonify, render_template
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import constants as C
from Stats import Stats
from functions import asn_name_query, get_ip_json, db_connect, get_list_of
from functions import is_transit, is_peer, reverse_dns_query, communities_count


app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True


@app.route('/', methods=['GET'])
def bgp_index():
    data = myStats.get_data()
    top_peers = data['top_n_peers']
    cidr_breakdown = data['cidr_breakdown']
    communities = data['communities']
    peers = data['peers']
    source_asn = C.DEFAULT_ASN
    source_asn_name = asn_name_query(C.DEFAULT_ASN)
    customer_bgp_community = C.CUSTOMER_BGP_COMMUNITY
    transit_bgp_community = C.TRANSIT_BGP_COMMUNITY
    peer_bgp_community = C.PEER_BGP_COMMUNITY
    return render_template('bgp.html', **locals())


@app.route('/bgp/api/v1.0/peers', methods=['GET'])
def get_peers():
    return(jsonify(get_list_of(peers=True)))


@app.route('/bgp/api/v1.0/customers', methods=['GET'])
def get_customers():
    return(jsonify(get_list_of(customers=True)))


@app.route('/bgp/api/v1.0/ip/<ip>', methods=['GET'])
def get_ip(ip):
    return jsonify(get_ip_json(ip, include_history=False))


@app.route('/bgp/api/v1.0/communities', methods=['GET'])
def get_communities():
    return jsonify(communities_count())


@app.route('/bgp/api/v1.0/ip/<ip>/history', methods=['GET'])
def get_history(ip):
    return jsonify(get_ip_json(ip, include_history=True))


@app.route('/bgp/api/v1.0/asn/<int:asn>', methods=['GET'])
def get_asn_prefixes(asn):
    db = db_connect()
    prefixes = []

    if asn == C.DEFAULT_ASN:
        routes = db.bgp.find({'origin_asn': None, 'active': True})
    else:
        routes = db.bgp.find({'origin_asn': asn, 'active': True})

    for prefix in routes:
        prefixes.append({'prefix': prefix['_id'],
                         'is_transit': is_transit(prefix),
                         'origin_asn': prefix['origin_asn'],
                         'name': asn_name_query(asn),
                         'nexthop_ip': prefix['nexthop'],
                         'nexthop_ip_dns': reverse_dns_query(prefix['nexthop']),
                         'nexthop_asn': prefix['nexthop_asn'],
                         'as_path': prefix['as_path'],
                         'updated': prefix['age']
                         })

    return jsonify({'asn': asn,
                    'name': asn_name_query(asn),
                    'origin_prefix_count': routes.count(),
                    'is_peer': is_peer(asn),
                    'origin_prefix_list': prefixes})


@app.route('/bgp/api/v1.0/stats', methods=['GET'])
def get_stats():
    return myStats.get_data(json=True)


@app.route('/bgp/api/v1.0/asn/<int:asn>/downstream', methods=['GET'])
def get_downstream_asns(asn):
    db = db_connect()
    asn_list = []
    large_query = 200
    downstream_asns = db.bgp.distinct('as_path.1', {'nexthop_asn': asn, 'active': True})
    for downstream in downstream_asns:
        if len(downstream_asns) > large_query:
            dns_name = "(LARGE QUERY - DNS LOOKUP DISABLED)"
        else:
            dns_name = asn_name_query(downstream)
        asn_list.append({'asn': downstream, 'name': dns_name})
    return jsonify({'asn': asn,
                    'name': asn_name_query(asn),
                    'downstreams_asns_count': len(asn_list),
                    'downstreams_asns': asn_list})


@app.route('/bgp/api/v1.0/asn/<int:asn>/originated', methods=['GET'])
def get_originated_prefixes(asn):
    db = db_connect()
    originated = []
    prefixes = db.bgp.find({'origin_asn': asn, 'active': True})
    for prefix in prefixes:
        originated.append(prefix['_id'])

    return jsonify({'asn': asn,
                    'name': asn_name_query(asn),
                    'originated_prefix_count': len(originated),
                    'originated_prefix_list': originated})


@app.route('/bgp/api/v1.0/asn/<int:asn>/nexthop', methods=['GET'])
def get_nexthop_prefixes(asn):
    db = db_connect()
    nexthop = []
    prefixes = db.bgp.find({'nexthop_asn': asn, 'active': True})
    for prefix in prefixes:
        nexthop.append(prefix['_id'])

    return jsonify({'asn': asn,
                    'name': asn_name_query(asn),
                    'nexthop_prefix_count': len(nexthop),
                    'nexthop_prefix_list': nexthop})


@app.route('/bgp/api/v1.0/asn/<int:asn>/transit', methods=['GET'])
def get_transit_prefixes(asn):
    db = db_connect()
    all_asns = db.bgp.find({'active': True})
    prefixes = []

    for prefix in all_asns:
        if prefix['as_path']:
            if asn in prefix['as_path']:
                prefixes.append(prefix['_id'])
            else:
                pass
        else:
            pass

    return jsonify({'asn': asn,
                    'name': asn_name_query(asn),
                    'transit_prefix_count': len(prefixes),
                    'transit_prefix_list': prefixes})


sched = BackgroundScheduler()
myStats = Stats()
threading.Thread(target=myStats.update_stats).start()
threading.Thread(target=myStats.update_advanced_stats).start()
sched.add_job(myStats.update_stats, 'interval', seconds=5)
sched.add_job(myStats.update_advanced_stats, 'interval', seconds=90)
sched.start()

if __name__ == '__main__':
    app.run(debug=True)
