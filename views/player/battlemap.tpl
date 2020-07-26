%if gm:
	%title = '[GM] {0} @ {1}'.format(game.title, game.active)
%else:
	%title = '[{0}] {1}'.format(player.name, game.title)
%end

%include("header", title=title)

<div class="scene">
	<div class="dice">
%for sides in [4, 6, 8, 10, 12, 20]:
		<img src="/static/d{{sides}}.png" onClick="rollDice({{sides}});"><br />
%end
	</div>

%width = 1000
%if gm:
	%width += 200
%end
	<div style="float: left;">
		<canvas id="battlemap" width="{{width}}" height="720"></canvas>
	</div>
	
	<div id="players"></div>

	<div id="rolls"></div>
</div>


%if gm:
<div class="gm">
	<form action="/gm/{{game.title}}/upload" method="post" enctype="multipart/form-data">
		<input name="file[]" type="file" multiple />
		<input type="submit" value="upload" />
	</form>

	<input type="button" onClick="clearRolls()" value="clearRolls" />
	<input type="button" onClick="clearVisible()" value="clearVisible" /><br />
	<span id="info"></span>
	<input type="checkbox" name="locked" id="locked" onChange="tokenLock()" /><label for="locked">Locked</label>
	<input type="button" onClick="tokenStretch()" value="stretch" />
	<input type="button" onClick="tokenClone()" value="clone" />
	<input type="button" onClick="tokenDelete()" value="delete" />
</div>
%else:
	<span id="info" style="display: none"></span>
	<input type="checkbox" style="display: none" name="locked" id="locked" onChange="tokenLock()" />
%end

<script>
var battlemap = $('#battlemap')[0];

/** Mobile controls not working yet
battlemap.addEventListener('touchstart', tokenGrab);
battlemap.addEventListener('touchmove', tokenMove);
battlemap.addEventListener('touchend', tokenRelease);
*/

// desktop controls
battlemap.addEventListener('mousedown', tokenGrab);
battlemap.addEventListener('mousemove', tokenMove);
battlemap.addEventListener('mouseup', tokenRelease);
battlemap.addEventListener('wheel', tokenWheel);

start('{{game.title}}');
</script>

%include("footer")

