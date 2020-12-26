#!/usr/bin/python3

from gevent import monkey; monkey.patch_all()
from bottle import *

import os, json, random, time, sys

from pony import orm
from orm import db, db_session, Token, Game, engine

__author__ = "Christian Glöckner"



# setup database connection
db.bind('sqlite', str(engine.data_dir / 'data.db'), create_db=True)
db.generate_mapping(create_tables=True)


# setup db_session to all routes
app = default_app()
app.catchall = not engine.debug
app.install(db_session)

# setup engine with cli args and db session
engine.setup(sys.argv) 


# --- GM routes ---------------------------------------------------------------

# decorator for GM-routes
def asGm(callback):
	def wrapper(*args, **kwargs):
		session = request.get_cookie('session')
		if session is None:
			# force login
			redirect('/vtt/join')
		return callback(*args, **kwargs)
	return wrapper


@get('/vtt/join')
@view('join')
def gm_login():
	return dict(engine=engine)

@post('/vtt/join')
def post_gm_login():
	name = engine.applyWhitelist(request.forms.gmname)
	if name is None:
		return {'gmname': ''}
	name = name.lower()
	if name in engine.gm_blacklist or len(name) < 3:
		return {'gmname': ''}
	
	ip  = request.environ.get('REMOTE_ADDR')
	sid = db.GM.genSession()
	
	if len(db.GM.select(lambda g: g.name == name)) > 0:
		# collision
		return {'gmname': ''}
	
	# create new GM
	gm = db.GM(name=name, ip=ip, sid=sid)
	gm.postSetup()
	
	response.set_cookie('session', name, path='/', expires=gm.expire)
	response.set_cookie('session', sid, path='/', expires=gm.expire)

	db.commit()
	return {'gmname': gm.name}

@get('/', apply=[asGm])
@view('gm')
def get_game_list():
	gm = db.GM.loadFromSession(request)
	if gm is None:
		redirect('/vtt/join')
	
	server = ''
	if engine.local_gm:
		server = 'http://{0}:{1}'.format(engine.getIp(), engine.port)
	
	# show GM's games
	return dict(engine=engine, gm=gm, server=server, dbScene=db.Scene)

@post('/vtt/import-game/<url>', apply=[asGm])
def post_import_game(url):  
	url_ok = False
	game   = None
	
	# check GM and url
	gm = db.GM.loadFromSession(request) 
	if gm is not None and db.Game.isUniqueUrl(gm, url):
		url_ok = True
	
	# upload file
	files = request.files.getall('file')
	if url_ok and len(files) == 1:
		fname = files[0].filename
		if fname.endswith('zip'):
			game = db.Game.fromZip(gm, url, files[0])
		
		else:
			game = db.Game.fromImage(gm, url, files[0])
	
	# returning status
	return {
		'url' : url_ok,
		'file': game is not None
	}

@get('/vtt/export-game/<url>', apply=[asGm])
def export_game(url):
	gm = db.GM.loadFromSession(request)
	if gm is None:
		redirect('/')
	
	# load game
	game = db.Game.select(lambda g: g.admin == gm and g.url == url).first()
	
	# export game to zip-file
	zip_file, zip_path = game.toZip()
	
	# offer file for downloading
	return static_file(zip_file, root=zip_path, download=zip_file, mimetype='application/zip')

@post('/vtt/delete-game/<url>', apply=[asGm])
@view('games')
def delete_game(url):
	gm = db.GM.loadFromSession(request)
	
	# load game
	game = db.Game.select(lambda g: g.admin == gm and g.url == url).first()
		
	# delete everything for that game
	# @note: doing by hand to avoid some weird cycle stuff (workaround)
	for s in game.scenes:
		for t in s.tokens:
			t.delete()
		s.backing = None
		s.delete()
	game.active = None
	game.clear() # also delete images from disk!
	game.delete()
	
	server = ''
	if engine.local_gm:
		server = 'http://{0}:{1}'.format(engine.getIp(), engine.port)
	
	return dict(gm=gm, server=server)

@post('/vtt/create-scene/<url>', apply=[asGm])
@view('scenes')
def post_create_scene(url):
	gm = db.GM.loadFromSession(request)
	
	# load game
	game = db.Game.select(lambda g: g.admin == gm and g.url == url).first()
	
	# create scene
	scene = db.Scene(game=game)
	db.commit()
	
	game.active = scene.id
	
	return dict(engine=engine, game=game)

@post('/vtt/activate-scene/<url>/<scene_id>', apply=[asGm])
@view('scenes')
def activate_scene(url, scene_id):
	gm = db.GM.loadFromSession(request)
	# load game
	game = db.Game.select(lambda g: g.admin == gm and g.url == url).first()
	game.active = scene_id

	db.commit() 
	
	return dict(engine=engine, game=game)

@post('/vtt/delete-scene/<url>/<scene_id>', apply=[asGm]) 
@view('scenes')
def activate_scene(url, scene_id):
	gm = db.GM.loadFromSession(request)
	# load game
	game = db.Game.select(lambda g: g.admin == gm and g.url == url).first()

	# delete given scene
	scene = db.Scene.select(lambda s: s.id == scene_id).first()
	scene.backing = None
	scene.delete()
	
	# check if active scene is still valid
	active = db.Scene.select(lambda s: s.id == game.active).first()
	if active is None:
		# check for remaining scenes
		remain = db.Scene.select(lambda s: s.game == game).first()
		if remain is None:
			# create new scene
			remain = db.Scene(game=game)
			db.commit()
		# adjust active scene
		game.active = remain.id
		db.commit()
	
	return dict(engine=engine, game=game)
	
@post('/vtt/clone-scene/<url>/<scene_id>', apply=[asGm]) 
@view('scenes')
def duplicate_scene(url, scene_id):
	gm = db.GM.loadFromSession(request)
	# load game
	game = db.Game.select(lambda g: g.admin == gm and g.url == url).first()
	
	# load required scene
	scene = db.Scene.select(lambda s: s.id == scene_id).first()
	
	# create copy of that scene
	clone = db.Scene(game=game)
	# copy tokens (but ignore background)
	for t in scene.tokens:
		if t.size != -1:
			n = db.Token(
				scene=clone, url=t.url, posx=t.posx, posy=t.posy, zorder=t.zorder,
				size=t.size, rotate=t.rotate, flipx=t.flipx, locked=t.locked
			)
	
	db.commit()
	
	game.active = clone.id 
	
	return dict(engine=engine, game=game)

# --- playing routes ----------------------------------------------------------

@get('/static/<fname>')
def static_files(fname):
	root = engine.data_dir / 'static'
	if not os.path.isdir(root) or not os.path.exists(root / fname):
		root = './static'
	
	return static_file(fname, root=root)

@get('/token/<gmname>/<url>/<fname>')
def static_token(gmname, url, fname):
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	path = game.getImagePath()
	
	return static_file(fname, root=path)

@post('/<gmname>/<url>/login')
#@view('redirect')
def set_player_name(gmname, url):
	playername = template('{{value}}', value=format(request.forms.playername))
	if playername is None:
		return {'playername': '', 'playercolor': ''}
	
	playercolor = request.forms.get('playercolor')
	
	# make player color less bright
	parts       = [int(playercolor[1:3], 16), int(playercolor[3:5], 16), int(playercolor[5:7], 16)]
	playercolor = '#'
	for c in parts:
		if c > 200:
			c = 200
		if c < 16:
			playercolor += '0'
		playercolor += hex(c)[2:]
	
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	
	# save playername in client cookie (expire after 30 days)
	expire = int(time.time() + 3600 * 24 * 30)
	response.set_cookie('playername', playername, path=game.getUrl(), expires=expire)
	response.set_cookie('playercolor', playercolor, path=game.getUrl(), expires=expire)
	
	return {'playername': playername, 'playercolor': playercolor}

@get('/<gmname>/<url>')
@view('battlemap')
def get_player_battlemap(gmname, url):
	# try to load playername from cookie (or from GM name)
	playername = request.get_cookie('playername')
	gm         = db.GM.loadFromSession(request)
	if playername is None:
		if gm is not None:
			playername = gm.name
		else:
			playername = ''
	
	# try to load playercolor from cookieplayercolor = request.get_cookie('playercolor')
	playercolor = request.get_cookie('playercolor')
	if playercolor is None:   
		colors = ['#ff0000', '#00ff00', '#0000ff', '#ffff00', '#ff00ff', '#00ffff']
		playercolor = colors[random.randrange(len(colors))]
	
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	
	if game is None:
		abort(404)
	
	user_agent = request.environ.get('HTTP_USER_AGENT')
	
	# show battlemap with login screen ontop
	return dict(engine=engine, user_agent=user_agent, game=game, playername=playername, playercolor=playercolor, is_gm=gm is not None)

# on window open
@post('/<gmname>/<url>/join')
def join_game(gmname, url):
	# load player name from cookie
	playername = request.get_cookie('playername')
	playercolor = request.get_cookie('playercolor')
	
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	game_url = game.getUrl()
	
	# save this playername
	engine.cache.insert(game, playername, playercolor)

# on window close
@post('/<gmname>/<url>/disconnect')
def quit_game(gmname, url):
	# load player name from cookie
	playername = request.get_cookie('playername')
	
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	game_url = game.getUrl()
	
	# remove playername and -color
	engine.cache.remove(game, playername)

@post('/<gmname>/<url>/update')
def post_player_update(gmname, url):
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	if game is None:
		return {}
	game_url = game.getUrl()
	
	if not engine.cache.contains(game):
		# game not found (should only be relevant for debugging)
		return {} 
	
	# load active scene
	scene = db.Scene.select(lambda s: s.id == game.active).first()
	
	# consider time and full updates
	now = time.time()                
	timeid = request.POST.get('timeid')
	timeid = float(timeid) if timeid is not None else 0.0
	full_update = bool(request.POST.get('full_update'))
	scene_id = request.POST.get('scene_id')
	if scene_id is None or int(request.POST.get('scene_id')) != scene.id:
		# scene has changed
		full_update = True
	
	# fetch token updates from client
	changes = json.loads(request.POST.get('changes'))
	
	# mark all selected tokens in that color
	playername = request.get_cookie('playername')
	ids = request.POST.get('selected')
	engine.cache.setSelection(game, playername, ids)
	
	# update token data
	for data in changes:
		token = scene.tokens.select(lambda s: s.id == data['id']).first()
		if token is not None:
			# check for set-as-background
			if data['size'] == -1:
				# delete previous background
				if scene.backing is not None:
					scene.backing.delete()
				scene.backing = token
			
			# update token
			token.update(
				timeid=timeid,
				pos=(int(data['posx']), int(data['posy'])),
				zorder=data['zorder'],
				size=data['size'],
				rotate=data['rotate'],
				flipx=data['flipx'],
				locked=data['locked']
			)

	# query token data for that scene
	tokens = list()
	for t in scene.tokens.select(lambda t: t.scene == scene):
		# consider token if it was updated after given timeid
		if t.timeid >= timeid or full_update:
			tokens.append(t.to_dict())
	
	# query rolls since last update (or last 10s)
	rolls = list()
	roll_timeid = timeid
	if roll_timeid == 0:
		roll_timeid = now - 10
	#for r in db.Roll.select(lambda r: r.game == game and r.timeid >= now - 10).order_by(lambda r: r.timeid)[:13]:
	for r in db.Roll.select(lambda r: r.game == game and r.timeid >= roll_timeid).order_by(lambda r: r.timeid):
		# query color by player
		color = engine.cache.getColor(game, r.player)
		
		# consider token if it was updated after given timeid
		rolls.append({
			'player' : r.player,
			'color'  : color,
			'sides'  : r.sides,
			'result' : r.result,
			'id'     : r.id,
			'timeid' : r.timeid
		})
	
	# query players alive
	playerlist = engine.cache.getList(game)
	
	# return tokens, rolls and timestamp
	data = {
		'active'   : game.active,
		'timeid'   : time.time(),
		'tokens'   : tokens,
		'rolls'    : rolls,
		'players'  : playerlist,
		'selected' : engine.cache.getSelected(game),
		'scene_id' : scene.id
	}
	return json.dumps(data)

@get('/<gmname>/<url>/range_query/<x:int>/<y:int>/<w:int>/<h:int>')
def range_query_token(gmname, url, x, y, w, h):
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	# load active scene
	scene = db.Scene.select(lambda s: s.id == game.active).first()
	
	# query all tokens in range
	token_ids = list()
	for t in db.Token.select(lambda t: t.scene == scene and x <= t.posx and t.posx <= x + w and y <= t.posy and t.posy <= y + h):
		if t.size != -1:
			token_ids.append(t.id)
	
	return json.dumps(token_ids)

@post('/<gmname>/<url>/roll/<sides:int>')
def post_roll_dice(gmname, url, sides):
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	# load active scene
	scene = db.Scene.select(lambda s: s.id == game.active).first()
	scene.timeid = time.time()
	
	# load player name from cookie
	playername = request.get_cookie('playername')
	
	# add player roll
	result = random.randrange(1, sides+1)
	db.Roll(game=game, player=playername, sides=sides, result=result, timeid=time.time())

@post('/<gmname>/<url>/upload/<posx:int>/<posy:int>')
def post_image_upload(gmname, url, posx, posy):
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	# load active scene
	scene = db.Scene.select(lambda s: s.id == game.active).first()
	scene.timeid = time.time()
	
	# upload all files to the current game
	# and create a token each
	files = request.files.getall('file[]')
	
	tokens = list(db.Token.select(lambda t: t.scene == scene))
	if len(tokens) > 0:
		bottom = min(tokens, key=lambda t: t.zorder).zorder - 1
		if bottom == 0:
			bottom = -1
		top    = max(tokens, key=lambda t: t.zorder).zorder + 1
	else:
		bottom = -1
		top = 1
	
	# place tokens in circle around given position
	n = len(files)
	if n > 0:
		for k, handle in enumerate(files):
			# move with radius-step towards y direction and rotate this position
			x, y = db.Token.getPosByDegree((posx, posy), k, n)
			
			kwargs = {
				"scene"  : scene,
				"timeid" : scene.timeid,
				"url"    : game.upload(handle),
				"posx"   : x,
				"posy"   : y
			}
			
			# determine file size to handle different image types
			size = game.getFileSize(kwargs["url"])
			if size < 250 * 1024:
				# files smaller 250kb as assumed to be tokens
				kwargs["zorder"] = top
				
			else:
				# files larger 250kb are handled as decoration (index cards) etc.)
				kwargs["size"]   = 300
				kwargs["zorder"] = bottom
			
			# create token
			t = db.Token(**kwargs)
			
			# use as background if none set yet
			if scene.backing is None:
				t.size = -1
				scene.backing = t
	
	db.commit()

@post('/<gmname>/<url>/clone/<x:int>/<y:int>')
def ajax_post_clone(gmname, url, x, y):
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	# load active scene
	scene = db.Scene.select(lambda s: s.id == game.active).first()
	# update position
	scene.timeid = time.time()
	# load token data
	token_ids = json.loads(request.POST.get('ids'))
	
	# clone tokens
	for k, tid in enumerate(token_ids):
		token = db.Token.select(lambda t: t.id == tid).first()
		if token is not None:
			pos = db.Token.getPosByDegree((x, y), k, len(token_ids))
			db.Token(scene=token.scene, url=token.url, posx=pos[0],
				posy=pos[1], zorder=token.zorder, size=token.size,
				rotate=token.rotate, flipx=token.flipx, timeid=time.time())

@post('/<gmname>/<url>/delete')
def ajax_post_delete(gmname, url):
	# load game
	game = db.Game.select(lambda g: g.admin.name == gmname and g.url == url).first()
	# load active scene
	scene = db.Scene.select(lambda s: s.id == game.active).first()
	# delete requested token
	token_ids = json.loads(request.POST.get('ids'))
	for tid in token_ids:
		token = db.Token.select(lambda t: t.id == tid).first()
		if token is not None:
			token.delete()

@error(404)
@view('error')
def error404(error):
	return dict(engine=engine)

# --- setup stuff -------------------------------------------------------------

engine.run()
