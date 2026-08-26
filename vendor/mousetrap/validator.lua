local M = {}

local function valid_number(value)
	return type(value) == "number" and value >= 0
end

local function validate_geometry(geometry)
	if type(geometry) ~= "table" then
		return false
	end

	if geometry.corner and not valid_number(geometry.corner) then
		return false
	end

	if geometry.edge and not valid_number(geometry.edge) then
		return false
	end

	return true
end

local function validate_motion(motion)
	if type(motion) ~= "table" then
		return true
	end

	if motion.timer and not valid_number(motion.timer) then
		return false
	end

	return true
end

local function validate_binding(binding)
	if type(binding) ~= "table" then
		return false
	end

	if type(binding.callback) ~= "function" then
		return false
	end

	return true
end

function M.validate(config)
	if type(config) ~= "table" then
		return false, "config must be table"
	end

	if config.geometry then
		for _, geometry in pairs(config.geometry) do
			if not validate_geometry(geometry) then
				return false, "invalid geometry"
			end
		end
	end

	if not validate_motion(config.motion) then
		return false, "invalid motion"
	end

	if config.binds then
		for _, binds in pairs(config.binds) do
			if type(binds) ~= "table" then
				return false, "invalid binds"
			end

			for _, binding in ipairs(binds) do
				if not validate_binding(binding) then
					return false, "invalid binding"
				end
			end
		end
	end

	return true
end

return M
