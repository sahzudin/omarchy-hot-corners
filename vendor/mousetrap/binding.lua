local M = {}

local next_id = 0

local function positive_number(value)
	if type(value) ~= "number" then
		return nil
	end

	if value < 0 then
		return nil
	end

	return value
end

local function copy_modifiers(modifiers)
	local result = {}

	if type(modifiers) ~= "table" then
		return result
	end

	for key, value in pairs(modifiers) do
		if value == true then
			result[key] = true
		end
	end

	return result
end

local function generate_id()
	next_id = next_id + 1

	return next_id
end

function M.new(callback, options)
	if type(callback) ~= "function" then
		error("mousetrap: callback must be a function")
	end

	options = options or {}

	local flick = positive_number(options.flick)

	local velocity = positive_number(options.velocity)

	local distance = positive_number(options.distance)

	local direction = type(options.direction) == "string" and options.direction or nil

	return {
		id = generate_id(),

		callback = callback,

		delay = (flick or velocity or direction or options.exit) and 0 or (positive_number(options.delay) or 0),

		flick_sq = flick and flick * flick or nil,

		velocity_sq = velocity and velocity * velocity or nil,

		direction = direction,

		distance = distance,

		exit = options.exit == true,

		loop = options.loop == true,

		priority = positive_number(options.priority) or 0,

		modifiers = copy_modifiers(options.modifiers or options.mod),
	}
end

return M
