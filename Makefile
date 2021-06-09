install-service:
	sudo cp pv.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable pv.service
	sudo systemctl restart pv.service

clean:
	@find -name "*.pyc" -delete
	@find -name "*~" -delete
	@find -name "__pycache__" -delete
	@find -name "*.tar" -delete
	@find -name "pv-switching-log.txt" -delete

tar: clean
	@echo "Building archive file: pv-switcher.tar"
	@tar --xform "s%^%pv-switcher/%" -cf pv-switcher.tar Makefile LICENSE README.md pv.service daily-scaling.txt py/
