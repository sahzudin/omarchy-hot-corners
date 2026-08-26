local M = {}

local levels = {
	error = 1,
	warn = 2,
	info = 3,
	debug = 4,
}

local current_level = levels.warn

local history = {}

local function push(level, message)
	history[#history + 1] = {
		level = level,
		message = message,
		time = os.time(),
	}

	if #history > 200 then
		table.remove(history, 1)
	end
end

function M.set_level(level)
	if levels[level] then
		current_level = levels[level]
	end
end

function M.log(level, message)
	if not levels[level] then
		return
	end

	if levels[level] <= current_level then
		push(level, message)

		if level ~= "debug" then
			print("[mousetrap][" .. level .. "]", message)
		end
	end
end

function M.error(message)
	M.log("error", message)
end

function M.warn(message)
	M.log("warn", message)
end

function M.info(message)
	M.log("info", message)
end

function M.debug(message)
	M.log("debug", message)
end

function M.history()
	return history
end

function M.clear()
	history = {}
end

return M
