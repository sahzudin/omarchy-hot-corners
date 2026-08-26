local M = {}

local Logger = nil

local errors = {
	count = 0,
	last = nil,
	history = {},
}

function M.init(logger)
	Logger = logger
end

function M.capture(err)
	errors.count = errors.count + 1
	errors.last = err

	errors.history[#errors.history + 1] = {
		message = err,
		time = os.time(),
	}

	if #errors.history > 100 then
		table.remove(errors.history, 1)
	end

	if Logger then
		Logger.error(tostring(err))
	end
end

function M.clear()
	errors.count = 0
	errors.last = nil
	errors.history = {}
end

function M.get()
	return errors
end

return M
