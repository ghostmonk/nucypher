clean:
	rm *.msgpack *.json
	rm -rf /tmp/hackathon

lsur:
	lsof -n | grep 115 | grep LISTEN

run-fleet:
	./tmux_ursula_fleet

show-fleet:
	tmux attach -t ursula-fleet

kill-fleet:
	tmux kill-session -t ursula-fleet

show-files:
	tree /tmp/hackathon
	ls -l *json *msgpack

run:
	python alicia.py

show-alice-config:
	ccat /tmp/hackathon/alice.json