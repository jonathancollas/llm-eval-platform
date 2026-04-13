.PHONY: test

test:
	cd backend && PYTHONPATH=. pytest -q
