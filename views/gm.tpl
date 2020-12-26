%include("header", title="GM {0}".format(gm.name))

%if len(gm.games) > 0:
<div class="dropdown" onClick="openDropdown();">
	<div id="preview">
	%include("games")
	</div>
	<img id="drophint" src="/static/bottom.png" />
</div>
%end

<div class="menu" ondragover="GmUploadDrag(event);" ondrop="GmUploadDrop(event, '{{gm.name}}');" onClick="closeDropdown();">  

<hr />

<h1>GAMES by {{gm.name}}</h1>

	<div class="form">
		<p>ENTER GAME NAME</p>
		<p><input type="text" id="url" value="" /></p>
		
		<div class="dropzone" id="dropzone">                                           
			<p>DRAG AM IMAGE TO START</p>
			<form id="uploadform" method="post" enctype="multipart/form-data">
				<input id="uploadqueue" name="file" type="file" />
			</form>
		</div>      
		
		<br />  
	</div>
<hr />

</div>

<script>
	$('#drophint').fadeIn(1000, 0.0);
</script>

%include("footer")
