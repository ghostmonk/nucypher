clean:
	rm -f *.json
	rm -rf /tmp/hackathon

show-fleet-listeners:
	lsof -n | grep 115 | grep LISTEN

run-fleet:
	./tmux_ursula_fleet

show-fleet:
	tmux attach -t ursula-fleet

kill-fleet:
	tmux kill-session -t ursula-fleet

run: clean
	python alicia.py
