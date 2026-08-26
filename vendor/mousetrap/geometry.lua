local M = {}

function M.get_zone_at_pos(x, y, monitor, geometry)
	if not monitor then
		return "none"
	end

	geometry = geometry or {}

	local scale = monitor.scale or 1

	if scale <= 0 then
		scale = 1
	end

	local width = monitor.width / scale
	local height = monitor.height / scale

	local transform = monitor.transform or 0

	if transform % 2 == 1 then
		width, height = height, width
	end

	local corner = geometry.corner or 4
	local edge = geometry.edge or 2

	if y < corner then
		if x < corner then
			return "top-left"
		end

		if x > width - corner then
			return "top-right"
		end

		if y < edge then
			return "top"
		end
	elseif y > height - corner then
		if x < corner then
			return "bottom-left"
		end

		if x > width - corner then
			return "bottom-right"
		end

		if y > height - edge then
			return "bottom"
		end
	elseif x < edge then
		return "left"
	elseif x > width - edge then
		return "right"
	end

	return "none"
end

return M
